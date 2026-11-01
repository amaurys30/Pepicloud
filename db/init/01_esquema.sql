-- PepiCloud: metadatos de documentos clinicos. Los archivos NO se guardan aqui (sin BLOB).

CREATE TABLE personas (
    id_persona          VARCHAR(10)  PRIMARY KEY,           -- numero de cedula
    tipo_identificacion VARCHAR(5)   NOT NULL DEFAULT 'CC',
    nombres             VARCHAR(100) NOT NULL,
    apellidos           VARCHAR(100) NOT NULL,
    fecha_nacimiento    DATE,
    creado_en           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ck_cedula_numerica CHECK (id_persona ~ '^[0-9]{5,10}$')
);

CREATE TABLE tipos_documento (
    id_tipo     SERIAL       PRIMARY KEY,
    codigo      VARCHAR(40)  NOT NULL UNIQUE,               -- 2do nivel de la ruta en S3
    descripcion VARCHAR(200) NOT NULL,
    CONSTRAINT ck_codigo_ruta CHECK (codigo ~ '^[A-Z0-9_]+$')
);

CREATE TABLE documentos (
    id_documento        UUID         PRIMARY KEY,
    id_persona          VARCHAR(10)  NOT NULL REFERENCES personas (id_persona),
    id_tipo             INT          NOT NULL REFERENCES tipos_documento (id_tipo),
    titulo              VARCHAR(200) NOT NULL,
    nombre_original     VARCHAR(255) NOT NULL,
    content_type        VARCHAR(100) NOT NULL,
    tamano_bytes        BIGINT       NOT NULL CHECK (tamano_bytes > 0),
    sha256_original     CHAR(64)     NOT NULL,              -- integridad del archivo original
    llave_objeto        VARCHAR(500) NOT NULL UNIQUE,       -- cedula/TIPO/AAAA/MM/uuid.ext.enc
    clave_datos_cifrada TEXT         NOT NULL,              -- data key cifrada por KMS
    nonce               VARCHAR(64)  NOT NULL,              -- IV de AES-256-GCM
    fecha_registro      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    retencion_hasta     TIMESTAMPTZ  NOT NULL,              -- fecha_registro + 30 min
    estado              VARCHAR(20)  NOT NULL DEFAULT 'ACTIVO',
    eliminado_en        TIMESTAMPTZ,
    CONSTRAINT ck_estado    CHECK (estado IN ('ACTIVO', 'ELIMINADO')),
    CONSTRAINT ck_retencion CHECK (retencion_hasta > fecha_registro)
);

-- Una fila por ubicacion fisica del documento: copia A, copia B y backup
CREATE TABLE copias_documento (
    id_copia            SERIAL       PRIMARY KEY,
    id_documento        UUID         NOT NULL REFERENCES documentos (id_documento),
    rol                 VARCHAR(10)  NOT NULL,
    endpoint            VARCHAR(100) NOT NULL,              -- http://localstack-a:4566
    bucket              VARCHAR(100) NOT NULL,
    llave_objeto        VARCHAR(500) NOT NULL,
    version_id          VARCHAR(100),                       -- VersionId devuelto por S3
    etag                VARCHAR(100),
    estado              VARCHAR(15)  NOT NULL DEFAULT 'PENDIENTE',
    ultima_verificacion TIMESTAMPTZ,
    CONSTRAINT ck_rol          CHECK (rol IN ('A', 'B', 'BACKUP')),
    CONSTRAINT ck_estado_copia CHECK (estado IN ('PENDIENTE','OK','FALLIDA','PERDIDA','ELIMINADA')),
    CONSTRAINT uq_copia_rol    UNIQUE (id_documento, rol)
);

-- Solo-insercion: quien hizo que y desde que copia se sirvio cada descarga
CREATE TABLE auditoria (
    id           BIGSERIAL   PRIMARY KEY,
    momento      TIMESTAMPTZ NOT NULL DEFAULT now(),
    servicio     VARCHAR(30) NOT NULL,
    accion       VARCHAR(30) NOT NULL,                      -- CARGA, DESCARGA, FAILOVER...
    id_documento UUID,
    detalle      JSONB
);

CREATE INDEX ix_documentos_busqueda ON documentos (id_persona, id_tipo, fecha_registro DESC);
CREATE INDEX ix_copias_estado       ON copias_documento (estado) WHERE estado <> 'OK';
CREATE INDEX ix_auditoria_documento ON auditoria (id_documento, momento DESC);

-- Inmutabilidad de metadatos (complementa el Object Lock de S3):
--  * durante la retencion: ningun UPDATE ni DELETE, ni del administrador
--  * despues: solo se permite marcar el documento como ELIMINADO
CREATE FUNCTION fn_proteger_documento() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF now() < OLD.retencion_hasta THEN
        RAISE EXCEPTION 'Documento % protegido hasta % (retencion activa): % rechazado',
            OLD.id_documento, OLD.retencion_hasta, TG_OP
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;

    IF (NEW.id_documento, NEW.id_persona, NEW.id_tipo, NEW.titulo, NEW.nombre_original,
        NEW.content_type, NEW.tamano_bytes, NEW.sha256_original, NEW.llave_objeto,
        NEW.clave_datos_cifrada, NEW.nonce, NEW.fecha_registro, NEW.retencion_hasta)
       IS DISTINCT FROM
       (OLD.id_documento, OLD.id_persona, OLD.id_tipo, OLD.titulo, OLD.nombre_original,
        OLD.content_type, OLD.tamano_bytes, OLD.sha256_original, OLD.llave_objeto,
        OLD.clave_datos_cifrada, OLD.nonce, OLD.fecha_registro, OLD.retencion_hasta) THEN
        RAISE EXCEPTION 'Documento %: solo se permite cambiar el estado', OLD.id_documento
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER tg_proteger_documento
    BEFORE UPDATE OR DELETE ON documentos
    FOR EACH ROW EXECUTE FUNCTION fn_proteger_documento();

-- TRUNCATE no dispara triggers de fila: se bloquea aparte
CREATE FUNCTION fn_bloquear_truncate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'TRUNCATE no permitido sobre %', TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

CREATE TRIGGER tg_sin_truncate_documentos BEFORE TRUNCATE ON documentos
    FOR EACH STATEMENT EXECUTE FUNCTION fn_bloquear_truncate();
CREATE TRIGGER tg_sin_truncate_auditoria  BEFORE TRUNCATE ON auditoria
    FOR EACH STATEMENT EXECUTE FUNCTION fn_bloquear_truncate();
