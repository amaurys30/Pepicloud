-- Cada servicio solo puede hacer lo que su rol necesita. Ninguno tiene DELETE.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO usr_registro, usr_consulta, usr_worker;

-- api-registro: registra personas, documentos y copias
GRANT SELECT, INSERT, UPDATE ON personas, documentos, copias_documento TO usr_registro;
GRANT SELECT ON tipos_documento TO usr_registro;
GRANT INSERT ON auditoria TO usr_registro;
GRANT USAGE ON SEQUENCE copias_documento_id_copia_seq, auditoria_id_seq TO usr_registro;

-- api-consulta: solo lectura; unicamente escribe en auditoria
GRANT SELECT ON personas, tipos_documento, documentos, copias_documento TO usr_consulta;
GRANT INSERT ON auditoria TO usr_consulta;
GRANT USAGE ON SEQUENCE auditoria_id_seq TO usr_consulta;

-- worker-backup: lee documentos y actualiza el estado de las copias
GRANT SELECT ON documentos TO usr_worker;
GRANT SELECT, INSERT, UPDATE ON copias_documento TO usr_worker;
GRANT INSERT ON auditoria TO usr_worker;
GRANT USAGE ON SEQUENCE copias_documento_id_copia_seq, auditoria_id_seq TO usr_worker;
