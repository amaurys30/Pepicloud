# Asistente Empresarial Inteligente basado en Model Context Protocol (MCP)

Proyecto de la asignatura **Sistemas Distribuidos**. Implementa un asistente empresarial que permite a un usuario final consultar y ejecutar operaciones sobre distintos sistemas de información (ERP, correo electrónico y una API pública) mediante lenguaje natural, usando **exclusivamente** el protocolo **MCP** como mecanismo de integración entre el modelo de lenguaje y los sistemas empresariales.

## Evaluación / Sustentación

- 📄 **Plan de pruebas:** [`Plan_de_Pruebas_y_Guion_Sustentacion.docx`](./Plan_de_Pruebas_y_Guion_Sustentacion.docx) — 23 ítems evaluados, pasos de prueba y resultados, ejecutados desde la aplicación web.
- 📄 **Tutorial de instalación y configuración de MCP:** [`Tutorial_Instalacion_Configuracion_MCP.docx`](./Tutorial_Instalacion_Configuracion_MCP.docx) — conceptualización, guía práctica con código y dos casos de estudio reales.
- 🎥 **Video de sustentación:** [enlace a YouTube](PEGAR_AQUÍ_EL_ENLACE)

## Arquitectura

```
Usuario final (navegador)
        │  http://localhost:5000
        ▼
Contenedor webapp (Flask + cliente MCP propio)
        │  API de Anthropic (Claude)         │  MCP sobre HTTP → puerto 8000
        ▼                                     ▼
   Claude (modelo)                    Contenedor mcp-server
                                              │ XML-RPC     │ OAuth2      │ HTTPS
                                              ▼             ▼             ▼
                                      Contenedor odoo   Gmail API    API pública TRM
                                              │            (externa)   (datos.gov.co)
                                              ▼
                                      Contenedor db (PostgreSQL)
```

**Principio de diseño:** el modelo de lenguaje no tiene acceso directo a Odoo, PostgreSQL, Gmail ni a la API de TRM. La aplicación web es el único punto de entrada del usuario final y actúa como cliente MCP: recibe el mensaje, se lo pasa a Claude junto con las herramientas disponibles, y cuando el modelo solicita usar una, la aplicación la ejecuta contra el servidor MCP. Toda interacción con los sistemas empresariales pasa exclusivamente por las herramientas expuestas por ese servidor.

> Durante el desarrollo se usó Claude Desktop como herramienta de depuración del servidor MCP, pero no forma parte de la arquitectura de la solución entregada.

## Estructura del repositorio

```
proyecto-mcp-odoo/
├── docker-compose.yml
├── Plan_de_Pruebas_y_Guion_Sustentacion.docx
├── Tutorial_Instalacion_Configuracion_MCP.docx
├── odoo/addons/
├── mcp-server/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── server.py
│   ├── tools/
│   │   ├── odoo_client.py / odoo_tools.py
│   │   ├── gmail_client.py / gmail_tools.py
│   │   ├── trm_client.py / trm_tools.py
│   │   ├── reportes_client.py / reportes_tools.py
│   │   └── excepciones.py
│   └── logs/trazabilidad.py
└── webapp/
    ├── Dockerfile
    ├── requirements.txt
    ├── .env.example
    ├── app.py            # servidor Flask
    ├── mcp_bridge.py      # cliente MCP propio + orquestación con la API de Claude
    └── templates/index.html
```

## Herramientas MCP expuestas

| Herramienta | Sistema | Descripción |
|---|---|---|
| `consultar_clientes` | Odoo | Lista de clientes |
| `consultar_productos` | Odoo | Catálogo con stock |
| `consultar_ventas` | Odoo | Órdenes de venta |
| `consultar_facturas` | Odoo | Facturas (filtro por estado) |
| `consultar_inventario` | Odoo | Existencias por producto |
| `consultar_correos_cliente` | Gmail | Correos por cliente/factura/asunto |
| `enviar_correo_cliente` | Gmail | Envío de correos |
| `consultar_trm` | API TRM | Tasa Representativa del Mercado |
| `convertir_moneda_a_cop` | API TRM | Conversión de moneda extranjera a COP |
| `generar_reporte_clientes` / `generar_reporte_facturas` | Odoo | Reportes en PDF o Excel |
| `consultar_trazabilidad` | Interno | Historial de invocaciones MCP registradas |

Cada invocación se registra automáticamente (herramienta, parámetros, duración, estado y resultado) mediante el decorador `@trazar`, persistido en SQLite.

## Cómo levantar el proyecto

1. Crear `mcp-server/.env` a partir de `mcp-server/.env.example`, con los datos de conexión a Odoo.
2. Colocar `credentials.json` de Gmail (obtenido en Google Cloud Console) dentro de `mcp-server/`.

   El archivo `token.json` **no se genera dentro de Docker** (el flujo de autorización de Google necesita abrir una ventana de navegador interactiva, y un contenedor no tiene pantalla). Se genera una única vez, fuera de Docker, así:
   ```bash
   cd mcp-server
   python -m venv venv
   venv\Scripts\activate          # Windows
   pip install -r requirements.txt
   python -c "from tools.gmail_client import enviar_correo; enviar_correo('tu_correo@gmail.com', 'Prueba', 'Generando token')"
   ```
   Esto abre el navegador para iniciar sesión y autorizar el acceso (usar la misma cuenta configurada como usuario de prueba en Google Cloud Console). Al terminar, queda creado `mcp-server/token.json`, que Docker sí puede usar directamente después, sin volver a pedir login.
3. Crear `webapp/.env` a partir de `webapp/.env.example`, con una API key propia de Anthropic ([console.anthropic.com](https://console.anthropic.com); el uso por API se factura aparte de una cuenta de claude.ai).
4. Levantar todo:
   ```bash
   docker compose up -d --build
   docker compose ps   # confirmar que db, odoo, mcp-server y webapp estén "Up"
   ```
5. Acceder a Odoo en `http://localhost:8069` (administración del ERP).
6. Acceder a la aplicación para el usuario final en **`http://localhost:5000`**.

> Ni `.env`, ni `credentials.json`, ni `token.json` están incluidos en este repositorio (excluidos en `.gitignore` por seguridad).

## Poblar Odoo con datos de prueba

Los datos de Odoo (clientes, productos, facturas) viven en un volumen de Docker generado en tiempo de ejecución y **no se incluyen en este repositorio**. Al clonar el proyecto y levantarlo por primera vez, Odoo inicia sin ningún dato: es necesario crearlos manualmente siguiendo estos pasos, una única vez, para poder reproducir los escenarios de prueba.

1. **Crear la base de datos:** entrar a `http://localhost:8069`, crear una base de datos nueva (por ejemplo `empresa_demo`), con país **Colombia**.
2. **Activar los módulos:** desde Aplicaciones, activar **Facturación** e **Inventario**.
3. **Activar multi-moneda:** en Facturación → Configuración → Monedas, habilitar **USD** además de la moneda local (COP).
4. **Crear clientes:** en Facturación → Clientes → Nuevo, crear al menos 5-6 clientes (mezcla de "Empresa" y "Persona"), con:
   - Al menos un cliente con país distinto a Colombia (para facturarle en USD).
   - Correos electrónicos reales de Gmail que se controlen, para probar el envío y la consulta de correos.
5. **Crear productos:** en Facturación → Productos → Nuevo, crear 6-8 productos ("Producto almacenable" o "Servicio"), con stock inicial variado (alto, bajo y en cero) desde Inventario.
6. **Crear facturas:** en Facturación → Clientes → Facturas → Nueva, crear varias facturas cubriendo los siguientes escenarios:
   - 2-3 facturas en **COP**, confirmadas.
   - Al menos 1 factura en **USD**, confirmada (para probar la conversión con la API de TRM).
   - Al menos 1 factura en **estado borrador** (sin confirmar), para mostrar variedad de estados.
7. **Ajustar la configuración del servidor MCP:** anotar el nombre exacto de la base de datos creada y el usuario/contraseña de administrador, y completarlos en `mcp-server/.env` (`ODOO_DB`, `ODOO_USER`, `ODOO_PASSWORD`).

Con estos datos, todas las herramientas del servidor MCP (`consultar_clientes`, `consultar_facturas`, `consultar_inventario`, la conversión con TRM, el envío y consulta de correos, y la generación de reportes) tienen información real suficiente para ejecutarse y demostrar cada escenario descrito en el plan de pruebas.

## Manejo de errores y resiliencia

Cada integración (Odoo, Gmail, TRM) devuelve un error controlado si el servicio no está disponible, en vez de un error crudo, y el resto del sistema sigue funcionando con normalidad. El servidor MCP reintenta la conexión a Odoo al arrancar (hasta 10 intentos con espera de 3s) para tolerar tiempos de inicialización del contenedor.

Prueba manual de resiliencia (sin reiniciar contenedores):
```bash
# Simular caída de Odoo
docker compose stop odoo
docker compose start odoo   # recuperación automática vía reintentos

# Simular caída de la API de TRM o de Gmail, sin reiniciar el servidor MCP
docker compose exec mcp-server sh -c "echo '127.0.0.1 www.datos.gov.co' >> /etc/hosts"
docker compose exec mcp-server sh -c "grep -v 'datos.gov.co' /etc/hosts > /tmp/hosts.nuevo && cat /tmp/hosts.nuevo > /etc/hosts"
```

## Autor

Sofía Suancha — Curso de Sistemas Distribuidos, 2026.
