# Asistencia Escolar QR — Backend

Especificación completa: `docs/INSTRUCCIONES_CLAUDE_CODE.md`. Diseño: `docs/diseno/*.html`.
App móvil (Expo) en otra carpeta: `C:\xampp\htdocs\app-asistencia-alumno`.

## Stack
- Django 5.2 LTS + DRF + SimpleJWT (access 30 min, refresh 30 días, rotación + blacklist)
- MySQL/MariaDB utf8mb4. XAMPP trae MariaDB 10.4 → backend `config.db.mysql_compat` (sin RETURNING)
- Windows + XAMPP, Python 3.12 en `.venv`. Servidor en el puerto **8001** (el 8000 lo usa otro proyecto)

## Comandos (PowerShell, desde esta carpeta)
```
.\.venv\Scripts\Activate.ps1
python manage.py runserver 0.0.0.0:8001
python -m pytest                       # SQLite en memoria (config.settings.test)
python manage.py makemigrations / migrate
python manage.py sembrar_demo --reset  # usuarios demo con contraseña Demo2026!
python manage.py qr_prueba --seccion 3B
python manage.py cerrar_dia [--fecha AAAA-MM-DD]
```

## Estructura
- `config/settings/{base,dev,prod,test}.py` — `.env` con django-environ (ver `.env.example`)
- `apps/comun` — ModeloBase, errores `{detalle, codigo}`, fechas Lima, permisos DRF
- `apps/cuentas` — Usuario (login por email, bloqueo) y **Rol** configurable; catálogo de permisos en `permisos.py`.
  El código pregunta `usuario.puede("permiso")`, nunca el nombre del rol. ADMIN siempre tiene todo.
- `apps/institucion` — Institución, AñoEscolar, Turno, DíaNoLectivo, Configuración, `sembrar_demo`
- `apps/academico` — Nivel, Grado, Sección, Curso, Asignación, BloqueHorario; `acceso.py` = quién ve/marca qué
- `apps/estudiantes` — Estudiante, Apoderado, Matrícula, Carnet (QR `AE1.<token>`, se guarda sha256)
- `apps/asistencia` — `reglas.py` (puras), `servicios.py` (aplicar_marca, escanear, justificar, cerrar_dia)
- `apps/reportes/servicios.py` (app móvil) y `agregados.py` (dashboard y reportes) — un solo cálculo para pantalla y exportes; `exportar.py` = Excel con colores
- `apps/panel` — panel web /panel/ (Django + HTMX + Alpine). Cada vista declara `permiso = "panel.x"`;
  el menú (`mixins.MENU`) se filtra por permisos. `importacion.py` = Excel/SIAGIE. Plantillas en `templates/panel/`
- `static/panel/` — tokens.css (colores del diseño), panel.css, fuentes y htmx/alpine locales (sin CDN)

## Convenciones
- Código, modelos y textos en español (Perú). Zona horaria America/Lima; guardar en UTC.
- Toda consulta de docente pasa por `apps/academico/acceso.py`; nunca confiar en IDs de la app.
- Reglas de negocio nuevas → `reglas.py` + test en `apps/asistencia/tests/test_reglas.py`.
- Errores de negocio: `raise ErrorNegocio("mensaje", "codigo", status_code=...)`.
- Sesión diaria: `bloque=None` → `bloque_clave=0` (la unicidad de MySQL no considera NULL).
- Idempotencia del lote: tabla `MarcaCliente` por `uuid_cliente`.
- Logs con IDs, nunca nombres de estudiantes (son menores).
- Nuevas dependencias: preguntar antes (lista fija en la sección 2 de la especificación).
- En plantillas, números para CSS/SVG con `floatformat:"1u"` (es-PE pone coma decimal).
- Carnets y reportes: hoja HTML A4 imprimible; PDF con WeasyPrint solo si importa (en Windows falta GTK).
- Antes de cerrar una tarea: `python manage.py check` y `python -m pytest` en verde.
