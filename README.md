# Asistencia Escolar QR — Backend (Django)

API REST para la app móvil de asistencia (docentes y auxiliares) de una I.E. de Primaria.
Stack: **Django 5.2 LTS + Django REST Framework + SimpleJWT + MySQL/MariaDB (XAMPP)**.

- Especificación completa: [`docs/INSTRUCCIONES_CLAUDE_CODE.md`](docs/INSTRUCCIONES_CLAUDE_CODE.md)
- Diseño (abrir en el navegador): [`docs/diseno/`](docs/diseno/)
- Pruebas de la API: [`api.http`](api.http)

## Instalación en Windows (XAMPP)

Abre **PowerShell** y ejecuta cada línea (copiar y pegar):

```powershell
# 1. Entrar a la carpeta del proyecto
cd C:\xampp\htdocs\asistencia-escolar-backend

# 2. Crear el entorno virtual con Python 3.12 (solo la primera vez)
py -3.12 -m venv .venv

# 3. Activarlo (verás "(.venv)" al inicio de la línea)
.\.venv\Scripts\Activate.ps1

# 4. Instalar las dependencias
pip install -r requirements.txt

# 5. Copiar la configuración y editarla si tu MySQL tiene contraseña
copy .env.example .env
```

> Si PowerShell no deja activar el entorno: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Luego:

1. Abre el **Panel de control de XAMPP** y presiona **Start** en **MySQL**.
2. Crea la base de datos (una sola vez):

   ```powershell
   C:\xampp\mysql\bin\mysql -u root -e "CREATE DATABASE asistencia_escolar CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
   ```

3. Crea las tablas y carga los datos de demostración:

   ```powershell
   python manage.py migrate          # crea las tablas
   python manage.py sembrar_demo     # I.E. demo: 12 secciones, ~300 alumnos, 20 días de asistencia
   ```

4. Levanta el servidor (el puerto 8000 lo usa otro proyecto, por eso **8001**):

   ```powershell
   python manage.py runserver 0.0.0.0:8001
   ```

   - **Panel de dirección:** <http://127.0.0.1:8001/panel/> (entra con `director@demo.edu.pe` o `admin@demo.edu.pe`)
   - Comprobar la API: <http://127.0.0.1:8001/api/v1/health/> → `{"estado": "ok"}`
   - Django Admin (depuración): <http://127.0.0.1:8001/admin/>

### Probar desde el teléfono (misma red Wi-Fi)

1. Busca la IP de tu PC: `ipconfig` → "Dirección IPv4" (ej. `192.168.1.50`).
2. En la app móvil usa `EXPO_PUBLIC_API_URL=http://192.168.1.50:8001/api/v1`.
3. Si no conecta, permite Python en el **Firewall de Windows** (redes privadas).

### MariaDB 10.4 de XAMPP

Django 5 pide MariaDB 10.5+. El proyecto usa un adaptador propio (`config/db/mysql_compat`)
que permite la 10.4 de XAMPP. En producción usa MySQL 8 o MariaDB 10.6+.

## Usuarios demo

Todos con la contraseña **`Demo2026!`** (cámbiala con `sembrar_demo --password ...`).

| Rol | Correo | Notas |
|---|---|---|
| Docente | `m.quispe@ie-ejemplo.edu.pe` | Marisol Quispe, tutora de 3.º A y 3.º B |
| Docentes | `r.huaman@`, `j.cusi@`, `e.mamani@`, `k.torres@`, `l.ccori@` + `ie-ejemplo.edu.pe` | Tutores de 1.º, 2.º, 4.º, 5.º y 6.º |
| Director | `director@demo.edu.pe` | Ve todas las secciones |
| Auxiliar | `auxiliar@demo.edu.pe` | Solo escanea (modo puerta) |
| Admin | `admin@demo.edu.pe` | Superusuario del Django Admin |

## Panel web

El panel abre en **Inicio**: la asistencia del día con sus estadísticas (KPIs, % por grado, últimos
15 días hábiles, secciones pendientes). El menú sigue el orden de trabajo: **Organización del año**
(Año escolar, Grados y secciones, Cursos y horarios, Calendario), **Personas** (Docentes, Estudiantes,
Importar, Carnets), **Asistencia** (Reportes) y **Sistema** (Usuarios y roles, Institución y reglas).
Quien no tiene permiso para ver la asistencia entra directo a la primera sección que sí puede ver.

### Año nuevo y paso de año

1. **Año escolar → Nuevo año escolar** (4 pasos): fechas de clases, qué copiar del año anterior (todo, solo
   secciones o nada) y cuándo activarlo. Los feriados nacionales se agregan solos. El año nuevo no se activa solo; la app sigue en el actual hasta pulsar **Activar**.
2. **Pasar de año**: por cada salón, todos pasan al grado siguiente (misma letra) con un clic. Solo se
   cambia a quien **repite** (otra sección del mismo grado) o **no continúa**. El último grado egresa por
   defecto. Se puede repetir sin duplicar matrículas; la matrícula del año anterior no se toca.

### Roles y permisos (todo configurable)

Cada usuario tiene **un rol**, y cada rol es una lista de **permisos** que se marcan en
**Usuarios y roles → Roles y permisos**. Se pueden crear roles nuevos (ej. *Subdirector*, *Secretaría*,
*Coordinador de TOE*) y renombrar o cambiar los iniciales. Los cambios se aplican al instante en el panel y,
al abrirse, en la app.

| Permiso | Qué habilita |
|---|---|
| Panel web (12) | Una casilla por cada sección del menú: Inicio (asistencia del día), Año escolar, Grados y secciones, Cursos y horarios, Calendario, Docentes, Estudiantes, Importar, Carnets, Reportes, Institución y reglas, Usuarios y roles |
| Ingresar a la app | Iniciar sesión en el teléfono |
| Pasar lista | Registrar en sus secciones (tutor o docente de curso) |
| Escanear en la puerta | Registrar el ingreso de cualquier estudiante con su carnet |
| Todas las secciones | Ver y registrar en todas las secciones |
| Justificar · Corregir días anteriores | Justificar faltas/tardanzas · editar días pasados con motivo |
| Historial · Contactar apoderados | Buscar estudiantes y ver su mes · ver y llamar al apoderado |
| Es docente | Puede ser tutor y tener cursos asignados |

Roles iniciales: **Administrador** (todo; no se puede recortar ni dejar al sistema sin un administrador activo),
**Director(a)**, **Docente** y **Auxiliar**. El menú del panel y las pestañas de la app solo muestran lo permitido.

### Datos de la institución

En **Configuración**: nombre, nombre corto, código modular, UGEL, dirección, teléfono, correo, **logo** e
**imagen de portada**. Se usan en el login del panel y de la app, el menú, el perfil de la app, los carnets y
los reportes. También: reglas de asistencia, turnos, años escolares y **Niveles y grados** (activar inicial/
primaria/secundaria, renombrar o agregar grados).

| Menú | Qué hace |
|---|---|
| Estudiantes | Búsqueda en vivo, ficha con apoderados, matrícula (retiro/traslado), carnet (imprimir, regenerar, dar de baja) |
| Grados y secciones | Secciones del año activo: grado, letra, turno, tutor, aula, capacidad |
| Docentes y asignaciones | Crear docente (contraseña temporal), tutoría, cursos por sección, restablecer contraseña |
| Cursos y horarios | Catálogo de áreas y horario semanal por sección. El curso lo dicta el tutor salvo que se elija otro docente; un bloque se agrega a varios días a la vez. Detecta choques de docente y de salón |
| Carnets QR | Hoja A4 por sección (8 carnets de 85,6 × 54 mm) o por estudiante. Cada carnet lleva el logo de la I.E. y el QR (sin foto) |
| Importar estudiantes | Plantilla Excel o nómina de SIAGIE → vista previa con errores por fila → importar |
| Calendario | Los feriados nacionales de cada año (incluida Semana Santa) se cargan solos. A mano solo se agregan el aniversario, feriados regionales, vacaciones y otros días sin clases |
| Usuarios y roles | Usuarios (crear, editar, restablecer clave, activar), roles y su matriz de permisos |
| Configuración | Institución (nombre, logo, portada…), reglas, turnos, años escolares, niveles y grados |
| Dashboard del día | KPIs, % por grado, últimos 15 días hábiles, tabla por sección, «Aún sin registrar». Filtros fecha y turno. Se actualiza cada 60 s. Excel y PDF |
| Reportes | Diario por sección · Resumen mensual (matriz con colores) · % por estudiante · Alertas de riesgo. Excel con colores y PDF (A4; el mensual en horizontal) |

**Imprimir carnets:** abre la hoja A4 y usa «Imprimir / Guardar como PDF» (A4, márgenes «Ninguno», escala 100 %).
El botón «Descargar PDF» directo aparece solo donde WeasyPrint funciona (servidor Linux); en Windows
necesitaría GTK, por eso se usa la impresión del navegador, que da la misma hoja.

**% de asistencia** en todo el sistema = (P + T + J) ÷ días registrados (regla 7), con 1 decimal y coma.

**Recordar a los docentes:** envía una notificación push (servicio de Expo) a los tutores con secciones
incompletas hoy, como máximo una vez cada 15 minutos. Solo llega a quienes tengan la app instalada con
notificaciones activas; el registro del token en la app llega con la build de EAS (Fase 7), porque Expo Go
no recibe notificaciones remotas en Android.

**Docentes: correo + DNI.** Al crear un docente su DNI es obligatorio y es su contraseña (no se le
obliga a cambiarla). Si la olvida o se bloquea, «Volver a la clave DNI» en su ficha la restablece.
Si se corrige el DNI y aún usaba el anterior como clave, la clave pasa al DNI nuevo.

**Primaria: el tutor dicta todo.** Al crear/editar una sección o asignar una tutoría, la casilla
«El tutor(a) dicta todos los cursos» le asigna los cursos que no tienen docente; al cambiar de tutor,
sus cursos pasan al nuevo. Los de otros docentes (Inglés, Educación Física) no se tocan.

**Contraseñas temporales** (usuarios sin DNI): al crear un usuario o restablecer su clave, el panel la muestra **una sola vez**.
El usuario debe cambiarla al entrar (en el panel o en la app).

## Comandos útiles

```powershell
python -m pytest                                  # tests (usan SQLite en memoria, no necesitan MySQL)
python manage.py sembrar_demo --reset             # borra y vuelve a crear los datos demo
python manage.py qr_prueba --seccion 3B           # PNG con los QR de 3.º B en .\qr_prueba
python manage.py cerrar_dia                       # cierra el día: F a los sin registrar
python manage.py cerrar_dia --fecha 2026-10-30
python manage.py createsuperuser                  # crear otro administrador
```

### Cierre automático a las 23:59 (Programador de tareas de Windows)

```powershell
schtasks /Create /SC DAILY /ST 23:59 /TN "AsistenciaCerrarDia" /TR "C:\xampp\htdocs\asistencia-escolar-backend\.venv\Scripts\python.exe C:\xampp\htdocs\asistencia-escolar-backend\manage.py cerrar_dia"
```

En Linux (cron): `59 23 * * * cd /ruta/backend && .venv/bin/python manage.py cerrar_dia`

## API `/api/v1/`

Errores siempre como `{ "detalle": "...", "codigo": "..." }`. Autenticación: `Authorization: Bearer <access>`.

| Método | Ruta | Uso |
|---|---|---|
| GET | `health/` · `institucion/` | Estado del servidor · nombre de la I.E. y año para la pantalla de login (sin token) |
| POST | `auth/login/` | `{email, password}` → `access`, `refresh`, `usuario`. Bloqueo 15 min tras 5 intentos |
| POST | `auth/refresh/` · `auth/logout/` | Renovar (rota el refresh) · cerrar sesión (`{refresh}`) |
| POST | `auth/cambiar-password/` | `{actual, nueva}` |
| GET | `me/` · POST `me/push-token/` | Perfil, institución, turnos, secciones · token de Expo Push |
| GET | `movil/hoy/` | Tarjetas de "Mis secciones" con contadores y estado del día |
| GET | `movil/nomina/` | Nómina + `carnet_hash` para el modo offline. Soporta `If-None-Match` (ETag → 304) |
| GET | `secciones/{id}/sesion/?fecha=&bloque=` | Pase de lista con el registro de cada alumno |
| POST | `secciones/{id}/sesion/cerrar/` | "Guardar lista" |
| POST | `asistencia/lote/` | Cola offline: hasta 200 marcas, idempotente por `uuid_cliente` |
| POST | `asistencia/escanear/` | `{codigo, modo: PUERTA\|SECCION, seccion_id?}` → `ok \| duplicado \| invalido \| otra_seccion` |
| POST | `registros/{id}/justificar/` | multipart: `motivo` (SALUD, FAMILIAR, TRAMITE, OTRO), `detalle`, `foto` |
| GET | `registros/{id}/justificacion/foto/` | Constancia (solo tutor y dirección) |
| GET | `estudiantes/?q=` | Buscador sin tildes (solo alumnos del docente) |
| GET | `estudiantes/{id}/historial/?mes=2026-09` | Indicadores, calendario, faltas/justificaciones, apoderado |

### Notas para la app móvil

- **QR del carnet:** `AE1.<token>`. Para validar offline: `sha256(token)` en hex == `carnet_hash` de la nómina.
- **Estado por hora (P/T):** el servidor lo calcula solo para escaneos QR. En marcas manuales manda el
  estado que eligió el docente (la app aplica la regla de "primera marca Presente" con `turno.tarde_desde`).
- **Lote:** cada marca lleva `uuid_cliente` (UUID v4), `matricula_id`, `seccion_id`, `fecha`, `estado`
  (`P|T|F|J` o `null` para quitar la marca), `metodo` y `marcado_en` (hora del teléfono, ISO 8601).
  Una `J` necesita `justificacion: {motivo, detalle}`. Respuesta por marca: `aplicada | duplicada | rechazada`
  con `codigo`, `registro_id` y `estado_final` (lo que la app debe mostrar).
- **Hora del teléfono:** se acepta si está entre −12 h y +5 min de la hora del servidor. Si no, se usa la del
  servidor y se marca `hora_corregida`.

## Estado del proyecto

- [x] Fase 0 — Proyecto, settings divididos, MySQL utf8mb4, DRF, CORS, usuario personalizado
- [x] Fase 1 — Modelos, Django Admin, `sembrar_demo`, `reglas.py` con tests
- [x] Fase 2 — API móvil completa con permisos por rol, idempotencia y tests
- [x] Fase 5 — Panel web (HTMX): CRUD, importar Excel/SIAGIE, carnets A4, configuración y calendario
- [x] Fase 6 — Dashboard y reportes (Excel/PDF), "Recordar a los docentes" (push)
- [ ] Fase 7 — Despliegue (Gunicorn + Nginx) y pulido
