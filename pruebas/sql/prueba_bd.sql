-- Prueba de la base de datos. Todo se deshace al final (ROLLBACK).
-- Se ejecuta como administrador a proposito: el trigger debe frenar incluso al admin.
\set ON_ERROR_STOP on
BEGIN;

INSERT INTO personas (id_persona, nombres, apellidos) VALUES ('1102345678', 'Paciente', 'De Prueba');

-- Documento reciente: retencion activa 30 minutos
INSERT INTO documentos (id_documento, id_persona, id_tipo, titulo, nombre_original, content_type,
       tamano_bytes, sha256_original, llave_objeto, clave_datos_cifrada, nonce, fecha_registro, retencion_hasta)
SELECT '00000000-0000-0000-0000-000000000001', '1102345678', id_tipo, 'Doc reciente', 'a.pdf',
       'application/pdf', 1000, repeat('a', 64),
       '1102345678/HISTORIA_CLINICA/2026/11/00000000-0000-0000-0000-000000000001.pdf.enc',
       'clave', 'nonce', now(), now() + interval '30 minutes'
FROM tipos_documento WHERE codigo = 'HISTORIA_CLINICA';

-- Documento veterano: su retencion vencio hace 1 minuto
INSERT INTO documentos (id_documento, id_persona, id_tipo, titulo, nombre_original, content_type,
       tamano_bytes, sha256_original, llave_objeto, clave_datos_cifrada, nonce, fecha_registro, retencion_hasta)
SELECT '00000000-0000-0000-0000-000000000002', '1102345678', id_tipo, 'Doc veterano', 'b.pdf',
       'application/pdf', 1000, repeat('b', 64),
       '1102345678/LABORATORIO/2026/11/00000000-0000-0000-0000-000000000002.pdf.enc',
       'clave', 'nonce', now() - interval '31 minutes', now() - interval '1 minute'
FROM tipos_documento WHERE codigo = 'LABORATORIO';

DO $$
DECLARE
    reciente CONSTANT uuid := '00000000-0000-0000-0000-000000000001';
    veterano CONSTANT uuid := '00000000-0000-0000-0000-000000000002';
    fallos int := 0;
BEGIN
    BEGIN
        UPDATE documentos SET titulo = 'alterado' WHERE id_documento = reciente;
        RAISE NOTICE 'FALLO 1. UPDATE durante la retencion fue aceptado'; fallos := fallos + 1;
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'OK    1. UPDATE durante la retencion rechazado';
    END;

    BEGIN
        DELETE FROM documentos WHERE id_documento = reciente;
        RAISE NOTICE 'FALLO 2. DELETE durante la retencion fue aceptado'; fallos := fallos + 1;
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'OK    2. DELETE durante la retencion rechazado';
    END;

    BEGIN
        UPDATE documentos SET estado = 'ELIMINADO' WHERE id_documento = reciente;
        RAISE NOTICE 'FALLO 3. Marcar ELIMINADO durante la retencion fue aceptado'; fallos := fallos + 1;
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'OK    3. Marcar ELIMINADO durante la retencion rechazado';
    END;

    BEGIN
        TRUNCATE documentos CASCADE;
        RAISE NOTICE 'FALLO 4. TRUNCATE fue aceptado'; fallos := fallos + 1;
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'OK    4. TRUNCATE rechazado';
    END;

    BEGIN
        UPDATE documentos SET llave_objeto = 'otra/ruta' WHERE id_documento = veterano;
        RAISE NOTICE 'FALLO 5. Cambiar datos tras la retencion fue aceptado'; fallos := fallos + 1;
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'OK    5. Cambiar datos tras la retencion rechazado';
    END;

    BEGIN
        UPDATE documentos SET estado = 'ELIMINADO', eliminado_en = now() WHERE id_documento = veterano;
        RAISE NOTICE 'OK    6. Tras la retencion se permite marcar ELIMINADO';
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'FALLO 6. Marcar ELIMINADO tras la retencion fue rechazado: %', SQLERRM;
        fallos := fallos + 1;
    END;

    BEGIN
        SET LOCAL ROLE usr_consulta;
        INSERT INTO personas (id_persona, nombres, apellidos) VALUES ('99999', 'X', 'Y');
        RESET ROLE;
        RAISE NOTICE 'FALLO 7. usr_consulta pudo insertar'; fallos := fallos + 1;
    EXCEPTION WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'OK    7. usr_consulta no puede insertar (solo lectura)';
    END;

    BEGIN
        SET LOCAL ROLE usr_registro;
        DELETE FROM auditoria;
        RESET ROLE;
        RAISE NOTICE 'FALLO 8. usr_registro pudo borrar la auditoria'; fallos := fallos + 1;
    EXCEPTION WHEN insufficient_privilege THEN
        RESET ROLE;
        RAISE NOTICE 'OK    8. usr_registro no puede borrar la auditoria';
    END;

    BEGIN
        INSERT INTO personas (id_persona, nombres, apellidos) VALUES ('11-AB', 'X', 'Y');
        RAISE NOTICE 'FALLO 9. Se acepto una cedula invalida'; fallos := fallos + 1;
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'OK    9. Cedula invalida rechazada';
    END;

    IF fallos = 0 THEN
        RAISE NOTICE 'RESULTADO: todas las pruebas de base de datos pasaron';
    ELSE
        RAISE NOTICE 'RESULTADO: % prueba(s) fallaron', fallos;
    END IF;
END;
$$;

ROLLBACK;
