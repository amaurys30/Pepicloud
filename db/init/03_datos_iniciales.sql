-- Tipos de documento. El codigo es el 2do nivel de la ruta: bucket/<cedula>/<CODIGO>/<AAAA>/<MM>/
INSERT INTO tipos_documento (codigo, descripcion) VALUES
    ('HISTORIA_CLINICA',   'Historia clinica'),
    ('LABORATORIO',        'Resultado de laboratorio'),
    ('IMAGEN_DIAGNOSTICA', 'Imagen diagnostica (RX, TAC, ecografia)'),
    ('FORMULA_MEDICA',     'Formula medica'),
    ('EPICRISIS',          'Epicrisis'),
    ('INCAPACIDAD',        'Certificado de incapacidad'),
    ('CONSENTIMIENTO',     'Consentimiento informado');
