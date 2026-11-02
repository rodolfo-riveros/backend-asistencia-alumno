# Asistencia Escolar QR — Instrucciones para Claude Code

> **Cómo usar este archivo:** colócalo en la raíz del repositorio junto con la carpeta `docs/diseno/` (el diseño en HTML). Abre Claude Code en esa carpeta y escribe:
> `Lee INSTRUCCIONES_CLAUDE_CODE.md completo y ejecuta la Fase 0. Al terminar cada fase detente, muéstrame cómo probarla y espera mi confirmación.`

---

## 0. Reglas de trabajo para Claude Code

1. **Trabaja por fases** (sección 11). No avances a la siguiente fase sin que el usuario confirme. Al cerrar cada fase entrega: qué se hizo, comandos para probarlo y checklist de aceptación marcado.
2. **El usuario no es programador experto.** Da comandos exactos copy-paste para Windows (PowerShell) y explica en una línea qué hace cada uno. Entorno local: **Windows + Laragon (MySQL 8)** + Python 3.12 + Node 20 LTS.
3. **El diseño manda.** Antes de construir cualquier pantalla abre su HTML en `docs/diseno/` y respeta colores, tamaños, textos, espaciados y estados. Si algo no está en el diseño, sigue los mismos tokens (sección 4).
4. **Todo el texto de la interfaz en español (Perú)**, zona horaria `America/Lima`, formato de fecha `Martes, 6 de octubre`, decimales con coma (`92,9 %`).
5. En la Fase 0 crea un `CLAUDE.md` corto (máx. 60 líneas) con: stack, comandos para levantar backend/móvil, convenciones y enlace a este archivo. Este archivo es la especificación completa; `CLAUDE.md` es el resumen de trabajo diario.
6. Escribe tests para las reglas de negocio (sección 6) antes de dar por terminada una fase. `pytest` en backend, `jest` en móvil para la lógica pura (cálculo de estado, cola offline).
7. No inventes dependencias raras: usa las de la sección 2. Si necesitas otra, pregunta.
8. Nunca guardes secretos en el código: usa `.env` (backend) y `app.config.ts` + variables `EXPO_PUBLIC_*` (móvil). Entrega `.env.example`.

---

## 1. Qué es el sistema

Sistema de control de asistencia para una **Institución Educativa de nivel Primaria** (1.º a 6.º grado, turnos mañana/tarde) en Perú.

- **Docentes** usan su **teléfono o tablet** (app React Native) para pasar lista de sus secciones, ya sea **escaneando el QR del carnet** de cada alumno o **marcando manualmente** (Presente / Tarde / Falta / Justificado).
- **Director / Administrador** usa un **panel web** (Django) para crear el año escolar, grados, secciones, cursos, horarios, docentes, asignaciones, importar estudiantes, imprimir carnets QR y ver reportes.
- Los **estudiantes no tienen cuenta** (son niños). El QR del carnet solo contiene un código interno opaco.

### Adaptación a Primaria (importante)
El diseño muestra también "Secundaria" en algunos datos de ejemplo. **El sistema se configura para Primaria**:
- Grados por defecto: 1.º a 6.º de Primaria. El modelo admite `nivel` para el futuro, pero el filtro "Nivel" del panel **solo aparece si hay más de un nivel activo** (por defecto, oculto).
- En primaria cada sección tiene un **docente tutor (de aula)** que pasa **asistencia diaria de ingreso**. Ese es el modo principal.
- Los **docentes de área** (Educación Física, Inglés, Arte, Religión, etc.) pueden pasar **asistencia por bloque de horario** si la institución lo activa (`modo_asistencia = DIARIA | DIARIA_Y_POR_BLOQUE`). Por defecto: `DIARIA`.
- Datos del **apoderado** (nombre, parentesco, celular) por estudiante, para contacto ante faltas.
- Lenguaje amable y simple; botones grandes (mín. 44 px de alto) porque se usan de pie, en el patio o en el aula.

---

## 2. Stack técnico (fijo)

### Backend + Panel administrador — `backend/`
| Pieza | Elección |
|---|---|
| Framework | **Django 5.1** + **Django REST Framework 3.15** |
| Auth API móvil | **djangorestframework-simplejwt** (access 30 min, refresh 30 días, rotación + blacklist) |
| Base de datos | **MySQL 8** (Laragon en local) con `mysqlclient`. Charset `utf8mb4`. |
| Panel web | **Plantillas Django + HTMX 2 + Alpine.js 3**, CSS propio con los tokens del diseño (sin framework CSS pesado). Gráficos: **Chart.js 4** o SVG generado en servidor como en el diseño. |
| Excel | `openpyxl` (exportar e importar) |
| PDF | `weasyprint` (reportes y hoja A4 de carnets) |
| QR | `segno` (genera SVG nítido para impresión) |
| Imágenes | `Pillow` (fotos de justificación; redimensionar a máx. 1600 px, JPEG 80) |
| Config | `django-environ` |
| CORS | `django-cors-headers` |
| Filtros API | `django-filter` |
| Tests | `pytest`, `pytest-django`, `factory-boy` |
| Notificaciones push | API HTTP de **Expo Push** (`exponent_server_sdk`) |

### App móvil — `mobile/`
| Pieza | Elección |
|---|---|
| Base | **Expo SDK (última estable) + React Native + TypeScript estricto** |
| Navegación | **Expo Router** (tabs + stack) |
| Escáner QR | **`expo-camera`** (`CameraView` con `barcodeScannerSettings={{ barcodeTypes: ['qr'] }}`) + linterna (`enableTorch`) |
| Datos servidor | **TanStack Query v5** + `axios` con interceptor de refresh JWT |
| Estado local | **Zustand** |
| Offline | **`expo-sqlite`** (cola de marcas pendientes + caché de nómina) y `@react-native-community/netinfo` |
| Tokens | `expo-secure-store` |
| Fotos | `expo-image-picker` (cámara y galería) + `expo-image-manipulator` (comprimir) |
| Fuentes | `@expo-google-fonts/bricolage-grotesque` y `@expo-google-fonts/figtree` |
| Iconos | `lucide-react-native` (el diseño usa trazos estilo Lucide) |
| Feedback | `expo-haptics` (vibración al escanear) + `expo-av`/`expo-audio` (beep corto) |
| Push | `expo-notifications` |
| Build | **EAS Build** (APK para Android como prioridad; iOS opcional) |

### Estructura del repositorio
```
asistencia-escolar/
├── CLAUDE.md
├── INSTRUCCIONES_CLAUDE_CODE.md
├── docs/
│   └── diseno/                 # HTML del diseño (ver sección 5)
├── backend/
│   ├── manage.py
│   ├── config/                 # settings (base.py, dev.py, prod.py), urls, wsgi
│   ├── apps/
│   │   ├── cuentas/            # Usuario, roles, login, perfil
│   │   ├── institucion/        # Institución, año escolar, calendario, configuración
│   │   ├── academico/          # Nivel, Grado, Sección, Curso, Asignación, Horario
│   │   ├── estudiantes/        # Estudiante, Apoderado, Matrícula, Carnet QR, importación
│   │   ├── asistencia/         # SesionAsistencia, Registro, Justificación, reglas
│   │   ├── reportes/           # consultas agregadas, exportes Excel/PDF
│   │   └── panel/              # vistas web HTMX del administrador
│   ├── templates/panel/
│   ├── static/panel/           # css/tokens.css, js/, fonts
│   ├── requirements.txt
│   └── .env.example
└── mobile/
    ├── app/                    # Expo Router
    │   ├── (auth)/login.tsx
    │   ├── (app)/(tabs)/index.tsx         # Mis secciones
    │   ├── (app)/(tabs)/escanear.tsx      # Escáner QR (modo puerta)
    │   ├── (app)/(tabs)/estudiantes.tsx   # buscador → historial
    │   ├── (app)/(tabs)/perfil.tsx
    │   ├── (app)/seccion/[id]/lista.tsx   # Pase de lista
    │   ├── (app)/seccion/[id]/escanear.tsx# Escáner dentro de la sección
    │   ├── (app)/justificar/[registroId].tsx  # bottom sheet modal
    │   └── (app)/estudiante/[id].tsx      # Historial
    ├── src/
    │   ├── api/  (cliente axios, endpoints tipados)
    │   ├── db/   (sqlite: esquema, cola, caché)
    │   ├── sync/ (motor de sincronización)
    │   ├── theme/ (tokens.ts, tipografía)
    │   ├── components/ (Chip, BotonEstado, TarjetaSeccion, Contadores, BarraProgreso, Avatar…)
    │   ├── store/
    │   └── utils/ (fechas Lima, reglas de estado)
    └── app.config.ts
```

---

## 3. Roles y permisos

| Rol | Dónde entra | Puede |
|---|---|---|
| `ADMIN` | Panel | Todo, incluida configuración de la institución y usuarios. |
| `DIRECTOR` | Panel (y app en solo lectura opcional) | Todo lo académico, reportes, justificar, regenerar carnets. No borra el año escolar. |
| `DOCENTE` | App | Ver **solo sus secciones/cursos asignados**, pasar lista, escanear, justificar en sus secciones, ver historial de sus alumnos. |
| `AUXILIAR` | App | **Modo puerta**: escanear el ingreso de cualquier estudiante del turno (pantalla 05 "Ingreso · Puerta principal"). Ver contador del día. No justifica. |

- Login con **correo + contraseña** (pantalla 01). Bloqueo temporal tras 5 intentos fallidos (15 min).
- "¿La olvidaste?" → el docente ve un mensaje "Pide a dirección que restablezca tu contraseña" (sin correo SMTP en v1). El admin restablece desde el panel y el sistema genera una contraseña temporal que obliga a cambiarla al entrar.
- Permisos en DRF con clases propias: `EsDocenteDeLaSeccion`, `EsAdminODirector`, `EsAuxiliar`. **Toda consulta del docente se filtra por sus asignaciones**; nunca confiar en IDs enviados por la app.

---

## 4. Sistema visual (tokens del diseño)

Crea `mobile/src/theme/tokens.ts` y `backend/static/panel/css/tokens.css` con exactamente estos valores.

### Colores
| Token | Hex | Uso |
|---|---|---|
| `ink` (primario) | `#14213D` | Texto principal, botón primario, sidebar del panel, QR |
| `inkDeep` | `#0B1427` | Hover, fondo del escáner |
| `bg` | `#F4F3EE` | Fondo de app y panel (crema) |
| `surface` | `#FFFFFF` | Tarjetas, inputs |
| `textMuted` | `#4B5565` | Texto secundario |
| `textSubtle` | `#5A6478` | Etiquetas en mayúsculas, pies |
| `textOnBtn` | `#3F4859` | Texto de botón de estado inactivo |
| `border` | `#E4E2DA` | Bordes de tarjetas y botones inactivos |
| `borderInput` | `#D6D3C8` | Bordes de inputs |
| `neutralChip` | `#ECEAE2` | Chip "Pendiente" |
| `disabled` | `#9AA1AE` | Fines de semana en calendario |
| `scanBg` / `scanGrid` | `#1A2336` / `#232D42` | Visor del escáner |
| `scanOk` | `#3FBF7F` | Punto "en vivo" del escáner |

**Estados de asistencia** (siempre estos 4, siempre este orden P · T · F · J):
| Estado | Código | Sólido (botón activo / celda fuerte) | Chip fondo | Chip texto |
|---|---|---|---|---|
| Presente | `P` | `#1E7A4C` | `#E3F1E8` | `#17603B` |
| Tarde | `T` | `#A35505` (punto `#B45F06`) | `#FBEEDB` | `#8A4A05` |
| Falta | `F` | `#B42318` | `#FBE4E1` | `#9A1F15` |
| Justificado | `J` | `#2453A6` | `#E2EAF7` | `#1E4590` |

Estados de sección: `Completa` (verde chip), `En curso` (ámbar chip), `Pendiente` / `Sin iniciar` (gris `#ECEAE2`/`#4B5565` en app; rojo chip en el panel).

### Tipografía
- **Títulos:** Bricolage Grotesque 700, `letter-spacing: -0.02em` (H1 login 36 px / line-height 1.05).
- **Cuerpo y UI:** Figtree 400/500/600/700. Base 16 px; etiquetas 14 px 600; secundarios 13 px.
- Etiquetas de contexto: 13 px, 600, mayúsculas, `letter-spacing: 0.08em`, color `textSubtle`.

### Formas
- Radios: inputs 12, botón primario 14, tarjetas 16–18, botones de estado 10, chips y avatares 999 (píldora).
- Alturas: input 52, botón primario 54, botón de estado 44, botones redondos del escáner 44.
- Pantalla móvil de referencia: **390 × 844**. Padding lateral 20–28.
- Avatares con **iniciales** (ApellidoPaterno[0] + PrimerNombre[0]), sin fotos de niños en v1.

---

## 5. Pantallas (el diseño está en `docs/diseno/`)

Cada HTML tiene estilos inline y, al final, un `<script type="text/x-dc">` con los **datos de ejemplo y la lógica de estados**: úsalo para entender qué es dinámico (`{{...}}`) y cómo se calculan los colores. `<sc-for>` es un bucle; `sc-raw-*` son etiquetas HTML normales. `00-tablero-completo.html` muestra todas juntas (ábrelo en el navegador).

### App móvil (docente / auxiliar)

**01 · Iniciar sesión** (`01-iniciar-sesion.html`)
- Logo (escudo con check), "I.E. [Nombre de la institución]" (dinámico desde config), título "Control de asistencia", subtítulo.
- Inputs correo y contraseña, enlace "¿La olvidaste?", botón "Ingresar →".
- Pie: leyenda de los 4 chips de estado + "Año escolar 2026 · Hora de Lima" (año dinámico).
- Errores bajo el input en `#9A1F15`. Botón con spinner al enviar.

**02 · Mis secciones** (`02-mis-secciones.html`) — pestaña inicial
- Cabecera: fecha de hoy ("Martes, 6 de octubre"), "Hola, {nombre}", avatar con iniciales → Perfil.
- Banda informativa: "**Ingreso 7:45** · tolerancia 10 min / Desde las 7:56 se marca tarde" (valores de la configuración del turno).
- "Mis secciones · N asignadas". Tarjeta por sección: badge grado+sección (`3.º` / `A`), nombre, "Primaria · Mañana · 28 estudiantes", chip de estado (Completa / En curso / Pendiente), barra apilada (verde = presentes, ámbar = tardes) y pie "**24** presentes · 2 tardes" + "4 sin registrar" o "Lista completa".
- Si el docente de área tiene bloques hoy, mostrar también tarjetas por bloque: "Educación Física · 4.º A · 10:15–11:00".
- Pull-to-refresh. Indicador de "sin conexión · N marcas por enviar" cuando aplique.
- **Tab bar inferior:** Secciones · Escanear QR · Estudiantes · Perfil.

**03 · Pase de lista** (`03-pase-de-lista.html`)
- Cabecera: volver, "3.º grado · Sección B", "Martes 6 oct · 27 estudiantes", botón "QR" (abre el escáner de esta sección).
- 4 contadores: Presentes / Tardes / Faltas / Justif. (en vivo).
- Buscador "Buscar estudiante" (filtra por apellidos o nombres, sin tildes) + botón "**Todos presentes**" (marca P solo a los que están sin marcar; pedir confirmación si hay más de 0 sin marcar).
- Fila por alumno (orden alfabético por apellidos): avatar iniciales, apellidos (negrita), nombres, hora de registro o "Sin marcar"; 4 botones P/T/F/J. Tocar el activo lo desmarca. Al tocar **J** abre la pantalla 04.
- Pie fijo: "N sin marcar" / "Todos registrados", "● Guardado automático · 7:58" y botón "Guardar lista" (cierra la sesión del día; sigue siendo editable hasta las 23:59 del mismo día por el docente; después solo dirección).
- **Guardado automático:** cada toque se guarda en la cola local al instante y se sincroniza en segundo plano (sección 8).

**04 · Justificar** (`04-justificar.html`) — bottom sheet sobre la lista
- Título "Justificar inasistencia", nombre del alumno.
- Motivo (selección única): **Salud · Motivo familiar · Trámite · Otro**.
- Detalle (opcional, máx. 300 caracteres).
- "Adjuntar foto del documento — Constancia, receta o papeleta" (cámara o galería, opcional, 1 foto, comprimida).
- Cancelar / Guardar. Al guardar, el estado queda `J` (también aplica sobre una `T`: tardanza justificada se guarda como `J` con `estado_original = T`).

**05 · Escáner QR** (`05-escaner-qr.html`)
- Dos modos con la misma UI:
  - **Modo sección** (desde el botón QR de la lista): banda superior "3.º B · Ingreso".
  - **Modo puerta** (tab "Escanear QR", auxiliar o docente): "Ingreso · Puerta principal", registra a cualquier estudiante del turno actual.
- Visor oscuro con cuadrícula, marco de 4 esquinas, botón cerrar, botón linterna, texto "Apunta al código QR del carnet".
- Tarjeta del último resultado: "✓ Presente registrado · 7:52", avatar, "Flores Cusi, Mateo Joaquín", "3.º grado · Sección B · Primaria". Si fue tarde → chip ámbar "Tarde registrada".
- Lista "Últimos escaneados · 132 hoy" con 3 tipos de resultado:
  - Éxito (P o T) con sección y estado.
  - **Duplicado**: "Ya registrado a las 7:41" (no cambia nada, vibración corta doble).
  - **Inválido**: "Código no válido — Carnet dado de baja o inexistente" (rojo, vibración larga).
  - **Otra sección** (solo en modo sección): "Pertenece a 5.º C — no se registró" (ámbar).
- Escaneo continuo: ignorar el mismo código durante 3 s para no duplicar lecturas; beep + háptico en cada lectura válida.
- **Funciona sin internet** (valida contra la nómina en caché, sección 8).

**06 · Historial del estudiante** (`06-historial-estudiante.html`)
- Cabecera "Historial", avatar, nombre completo, "3.º grado · Sección B · Primaria".
- 3 indicadores del mes: "95 % Asistencia del mes", "2 Tardanzas", "1 Faltas · 1 justif.".
- Calendario mensual L–D con navegación ‹ mes ›: cada día hábil con su letra P/T/F/J y color (P y T en chip suave, F y J en sólido); fines de semana y días no lectivos en gris sin letra.
- Lista "Faltas y justificaciones": "Justificado · **Jue 17 sep** · Salud, con constancia", "Falta · **Mié 9 sep** · Sin justificar". Tocar una falta propia de hoy o editable → abre Justificar.
- Botón "Llamar al apoderado" (abre `tel:`) — solo visible para el tutor.

**Perfil** (no está en el diseño; seguir tokens): nombre, rol, correo, secciones asignadas, cambiar contraseña, estado de sincronización (última sync, marcas pendientes, botón "Sincronizar ahora"), cerrar sesión, versión de la app.

### Panel web (director / admin) — ancho de referencia 1440 px
Layout: **sidebar azul `#14213D`** (logo + "Asistencia · I.E. [Nombre]"), menú, pie con usuario y "Cerrar sesión". Contenido en fondo crema, tarjetas blancas.

Menú: Dashboard del día · Reportes · Estudiantes · Grados y secciones · Docentes y asignaciones · Cursos y horarios · Carnets QR · Importar estudiantes · Configuración.

**Panel · Dashboard del día** (`panel-01-dashboard-dia.html`)
- Encabezado: "Martes, 6 de octubre de 2026 · actualizado 8:14", "Asistencia de hoy", filtro Nivel (oculto si solo Primaria) → reemplazar por filtro **Turno** (Todos / Mañana / Tarde), botones **Excel** y **PDF**.
- 6 tarjetas KPI: Asistencia general (% y "702 de 757 registrados"), Presentes, Tardes ("después de 7:55"), Faltas, Justificados, Sin registrar ("en 3 secciones").
- "Asistencia por grado" (barras horizontales 1.º–6.º primaria, eje 80–100 %, barra ámbar si < 90 %).
- "Últimos 15 días hábiles": línea de asistencia % + línea de tardanzas (escala propia 0–10 %).
- Tabla "Por sección": Sección + tutor, barra de registro `15/27`, P, T, F, J, Estado (chip).
- "Aún sin registrar": por sección, tutor, hasta 3 nombres + "+N"; botón **"Recordar a los docentes"** (envía push a los tutores con secciones incompletas; máx. 1 vez cada 15 min).
- Auto-refresco cada 60 s con HTMX (`hx-trigger="every 60s"`).

**Panel · Reporte mensual** (`panel-02-reporte-mensual.html`)
- Pestañas: **Diario por sección · Resumen mensual · % por estudiante · Alertas de riesgo**.
- Filtros: Mes, Grado, Sección, Estudiante (búsqueda).
- Matriz estudiante × días hábiles con letra y color por celda, totales P/T/F/J y %. Leyenda arriba. Pie: "% = (presente + tarde + justificado) ÷ días hábiles".
- Lateral: "Alerta de riesgo — 3 o más faltas, o 4 o más tardanzas en el mes" con lista; "Promedio de la sección".
- Exportar **Excel** (misma matriz, con colores de celda) y **PDF** (A4 horizontal).

**Panel · Carnets por sección (A4)** (`panel-03-carnets-a4.html`)
- Hoja A4 vertical, 8 carnets por hoja (2 × 4), tamaño tarjeta **85,6 × 54 mm**, línea punteada de corte.
- Carnet: "I.E. [Nombre]" + año, avatar iniciales, "Estudiante", apellidos, nombres, "3.º B · Primaria", QR a la derecha.
- Encabezado de hoja: "Carnets de asistencia · hoja 1 de 4 — 3.º grado · Sección B · Primaria".
- Nota al pie (texto exacto): "El QR contiene solo un código interno del estudiante (sin DNI ni datos personales). Si se pierde el carnet, regenera el código desde el panel y el anterior deja de funcionar."
- Generar PDF por sección o por estudiante individual. Opción de logo de la I.E. (subido en Configuración).

**Pantallas CRUD del panel** (no diseñadas: usar el mismo layout, tablas como "Por sección", formularios con inputs del login):
- **Estudiantes:** lista con búsqueda/filtros, ficha (datos, apoderados, matrícula, historial, carnet: ver/regenerar/dar de baja).
- **Grados y secciones:** por año escolar; crear sección (grado, letra, turno, tutor, aula, capacidad).
- **Docentes y asignaciones:** crear docente (genera usuario), asignar tutoría y cursos por sección.
- **Cursos y horarios:** catálogo de cursos/áreas de primaria; horario semanal por sección (grilla L–V × bloques) con docente por bloque; detectar choques (mismo docente en dos bloques a la vez).
- **Importar estudiantes:** subir Excel (plantilla descargable). Columnas: `codigo_estudiante, dni (opcional), apellido_paterno, apellido_materno, nombres, sexo, fecha_nacimiento, grado, seccion, apoderado_nombre, apoderado_parentesco, apoderado_celular`. Compatible con la nómina exportada de **SIAGIE** (mapear columnas por nombre de encabezado). Vista previa con errores por fila antes de confirmar; importación en transacción.
- **Configuración:** datos de la I.E. (nombre, código modular, logo), año escolar activo, turnos (hora de ingreso, tolerancia, hora límite para falta), modo de asistencia, calendario (feriados y vacaciones), umbrales de alerta, usuarios.

---

## 6. Reglas de negocio (implementar en `apps/asistencia/reglas.py` + tests)

1. **Estado automático por hora** (QR o primera marca "Presente"):
   - `hora <= ingreso + tolerancia` → `P`. Con ingreso 7:45 y tolerancia 10 → P hasta **7:55:59**.
   - `hora > ingreso + tolerancia` y `<= hora_limite_falta` (por defecto ingreso + 120 min) → `T`.
   - Después de `hora_limite_falta` el escaneo registra `T` pero muestra advertencia; la decisión final es del docente.
   - El docente siempre puede sobrescribir manualmente; se guarda quién y cuándo (auditoría).
2. **Una marca por estudiante por sesión.** Re-escaneo = duplicado, no cambia el estado.
3. **Sesión de asistencia** = (sección, fecha, bloque de horario opcional). Se crea automáticamente al primer registro. En modo `DIARIA` hay una sola por sección y día.
4. **Cierre automático:** a las 23:59 (job diario) los alumnos sin marcar de sesiones abiertas quedan como `F` (configurable: `auto_falta_al_cierre = true`). Días no lectivos no generan sesiones.
5. **Edición:** el docente edita sus registros solo el mismo día. Director/Admin edita cualquier fecha, con motivo obligatorio. Todo cambio queda en `RegistroHistorial`.
6. **Justificación:** convierte `F` o `T` en `J`, conserva `estado_original`. Motivo obligatorio; foto opcional. Director puede aprobar/rechazar (v1: se aprueban al crearse; dejar el campo `estado_revision` preparado).
7. **% de asistencia** = `(P + T + J) ÷ días hábiles registrados` × 100, con 1 decimal y coma.
8. **Días hábiles** = lunes a viernes del año escolar menos feriados/vacaciones de `DiaNoLectivo`.
9. **Alerta de riesgo (mensual):** `faltas >= 3` **o** `tardanzas >= 4` (umbrales configurables). Lista en reporte y badge en ficha del estudiante.
10. **Carnet QR:** contenido = `AE1.<token>` donde `token` es aleatorio de 22 caracteres (`secrets.token_urlsafe(16)`). En BD guardar el token y su `sha256`. Regenerar invalida el anterior (estado `REVOCADO`). Estudiante retirado → carnet `BAJA`. **Nunca** DNI ni nombre dentro del QR.
11. Todas las horas se guardan en UTC y se calculan/visualizan en `America/Lima`. La hora válida del registro es **la del dispositivo al momento de marcar** (`marcado_en`), enviada por la app; el servidor la acepta si está entre −12 h y +5 min de su reloj, si no usa la del servidor y lo marca `hora_corregida = true`.

---

## 7. Modelo de datos (Django)

Usar `BigAutoField`, `creado_en`/`actualizado_en` en un modelo base abstracto, y `PROTECT` en FKs académicas.

```
cuentas.Usuario(AbstractUser)    email único (login), rol [ADMIN, DIRECTOR, DOCENTE, AUXILIAR],
                                 nombres, apellidos, celular, debe_cambiar_password, expo_push_token
institucion.Institucion          nombre, codigo_modular, ugel, logo, direccion           (registro único)
institucion.AnioEscolar          anio, fecha_inicio, fecha_fin, activo (solo uno activo)
institucion.Turno                nombre [MANANA, TARDE], hora_ingreso, tolerancia_min, hora_limite_falta
institucion.DiaNoLectivo         anio_escolar, fecha, motivo [FERIADO, VACACIONES, OTRO], descripcion
institucion.Configuracion        modo_asistencia, auto_falta_al_cierre, umbral_faltas, umbral_tardanzas
academico.Nivel                  nombre [INICIAL, PRIMARIA, SECUNDARIA], activo   (por defecto solo PRIMARIA)
academico.Grado                  nivel, numero (1–6), nombre ("3.º grado"), orden
academico.Seccion                anio_escolar, grado, letra, turno, tutor(Usuario DOCENTE), aula, capacidad
                                 unique(anio_escolar, grado, letra)
academico.Curso                  nombre (Matemática, Comunicación, Personal Social, Ciencia y Tecnología,
                                 Arte y Cultura, Educación Física, Educación Religiosa, Inglés, Tutoría), activo
academico.Asignacion             seccion, curso, docente   unique(seccion, curso)
academico.BloqueHorario          seccion, asignacion, dia_semana (1–5), hora_inicio, hora_fin
estudiantes.Estudiante           codigo_estudiante (único), dni (opcional, único si existe), apellido_paterno,
                                 apellido_materno, nombres, sexo, fecha_nacimiento, activo
estudiantes.Apoderado            estudiante, nombre, parentesco, celular, es_principal
estudiantes.Matricula            estudiante, seccion, anio_escolar, estado [ACTIVA, RETIRADO, TRASLADADO],
                                 fecha_alta, fecha_baja   unique(estudiante, anio_escolar)
estudiantes.Carnet               estudiante, token, token_hash, estado [ACTIVO, REVOCADO, BAJA], emitido_en
asistencia.SesionAsistencia      seccion, fecha, bloque (null = diaria), abierta_por, estado [ABIERTA, CERRADA],
                                 cerrada_en   unique(seccion, fecha, bloque)
asistencia.Registro              sesion, matricula, estado [P, T, F, J], estado_original, metodo [QR, MANUAL, AUTO],
                                 marcado_en, marcado_por, dispositivo_id, uuid_cliente (único, idempotencia),
                                 hora_corregida   unique(sesion, matricula)
asistencia.Justificacion         registro (1–1), motivo [SALUD, FAMILIAR, TRAMITE, OTRO], detalle, foto,
                                 creada_por, estado_revision [APROBADA, PENDIENTE, RECHAZADA]
asistencia.RegistroHistorial     registro, estado_anterior, estado_nuevo, cambiado_por, motivo, cambiado_en
```

Índices: `Registro(sesion, estado)`, `SesionAsistencia(fecha)`, `Matricula(seccion, estado)`, `Carnet(token_hash)`.

**Datos semilla** (`python manage.py sembrar_demo`): institución "I.E. [Nombre de la institución]", año 2026, turnos mañana (7:45 / 10 min) y tarde (12:45 / 10 min), grados 1.º–6.º, secciones A y B por grado, cursos de primaria, 1 director (`director@demo.edu.pe`), 6 docentes (incluida `m.quispe@ie-ejemplo.edu.pe` "Marisol Quispe" con 3.º A y 3.º B), 1 auxiliar, ~25 alumnos por sección con nombres peruanos como los del diseño, feriados nacionales de Perú 2026 y 20 días hábiles de asistencia aleatoria realista (≈92 % asistencia, ≈5 % tardanzas).

---

## 8. Modo offline y sincronización (crítico)

La I.E. puede tener mala señal. La app **debe funcionar sin internet** para pasar lista y escanear.

1. **Caché de nómina:** al abrir sesión y cada vez que hay red, la app descarga `GET /api/v1/movil/nomina/` → secciones del docente (o del turno, si es auxiliar) con alumnos y `token_hash` de carnets activos. Se guarda en SQLite con `version` (ETag). El escáner valida `sha256(token)` contra esta tabla.
2. **Cola de marcas:** cada toque o escaneo crea una fila en `cola_registros` (`uuid_cliente`, matricula_id, seccion_id, fecha, bloque_id, estado, metodo, marcado_en, intentos). La UI se actualiza desde SQLite, no desde la red.
3. **Envío:** cuando hay red, `POST /api/v1/asistencia/lote/` con hasta 200 marcas. El servidor es **idempotente por `uuid_cliente`** y responde por cada marca: `aplicada | duplicada | rechazada(motivo)`. Reintento con backoff (5 s, 30 s, 2 min, 10 min).
4. **Conflictos:** gana la marca con `marcado_en` más reciente, **excepto** que una `J` creada en el panel nunca se pisa desde la app. El servidor devuelve el estado final y la app lo refleja.
5. **Justificaciones con foto:** se encolan aparte; la foto se sube con `multipart` cuando hay red.
6. Indicador visible: "Sin conexión · 12 marcas por enviar" en Mis secciones y Perfil; "● Guardado automático · hh:mm" en la lista.
7. Tests de la cola en `jest` (sin red, con red, duplicados, conflicto).

---

## 9. API REST (`/api/v1/`)

Respuestas JSON, fechas ISO 8601, paginación por cursor donde aplique, errores `{ "detalle": "...", "codigo": "..." }` en español.

| Método | Ruta | Uso |
|---|---|---|
| POST | `auth/login/` | correo + contraseña → `access`, `refresh`, `usuario` |
| POST | `auth/refresh/` · `auth/logout/` | refresh / blacklist |
| POST | `auth/cambiar-password/` | |
| GET | `me/` | perfil, rol, institución (nombre, logo), turno y reglas de hora |
| POST | `me/push-token/` | registrar token Expo |
| GET | `movil/hoy/` | tarjetas de "Mis secciones" con contadores y estado del día |
| GET | `movil/nomina/` | nómina + hashes de carnets para modo offline (ETag) |
| GET | `secciones/{id}/sesion/?fecha=&bloque=` | sesión del día con registros por alumno |
| POST | `asistencia/lote/` | envío de marcas (idempotente) |
| POST | `asistencia/escanear/` | `{ codigo, seccion_id?, modo }` → resultado (`ok`, `duplicado`, `invalido`, `otra_seccion`) + alumno + estado. Usado cuando hay red; offline se resuelve local |
| POST | `secciones/{id}/sesion/cerrar/` | "Guardar lista" |
| POST | `registros/{id}/justificar/` | multipart: motivo, detalle, foto |
| GET | `estudiantes/?q=` | buscador (solo alumnos del docente) |
| GET | `estudiantes/{id}/historial/?mes=2026-09` | indicadores, días del calendario, faltas/justificaciones |

Endpoints del panel: se resuelven con vistas Django + HTMX (no necesitan API pública), pero reutiliza los mismos servicios de `reportes/servicios.py` para no duplicar cálculos.

Seguridad: rate limit en login y escanear (`DEFAULT_THROTTLE_RATES`), HTTPS en producción, fotos servidas solo a usuarios autorizados (vista protegida, no `MEDIA_URL` pública).

---

## 10. Privacidad (son menores de edad)

- Cumplir la **Ley N.º 29733 de Protección de Datos Personales (Perú)**: mínimo de datos, acceso por rol, sin datos personales en el QR.
- No guardar fotos de los niños en v1 (avatares con iniciales).
- Fotos de constancias: acceso solo para el tutor de la sección y dirección; borrado automático al cierre del año + 1 año (comando de mantenimiento).
- Logs sin nombres de estudiantes; usar IDs.
- En el dispositivo, la caché SQLite se borra al cerrar sesión.

---

## 11. Plan de fases (con criterios de aceptación)

### Fase 0 — Repositorio y entorno
- Crear estructura de carpetas, `CLAUDE.md`, `.gitignore`, `README.md` con pasos de instalación en Windows + Laragon.
- Backend: proyecto Django con settings divididos, conexión MySQL (`asistencia_escolar`, utf8mb4), `django-environ`, DRF, CORS. App `cuentas` con usuario personalizado **antes de la primera migración**.
- Móvil: `npx create-expo-app@latest mobile --template` (TypeScript), Expo Router, fuentes y `tokens.ts`.
- ✅ `python manage.py runserver` responde en `/api/v1/health/`; `npx expo start` abre una pantalla de prueba con las fuentes y colores del diseño en Expo Go.

### Fase 1 — Modelos, admin base y datos demo
- Todos los modelos de la sección 7, migraciones, registro en Django Admin (útil para depurar), comando `sembrar_demo`.
- `reglas.py` con tests de: cálculo P/T por hora, % asistencia, días hábiles, alerta de riesgo.
- ✅ `pytest` en verde; Django Admin muestra datos demo coherentes.

### Fase 2 — API móvil
- Auth JWT, `me`, `movil/hoy`, `nomina`, `sesion`, `lote`, `escanear`, `cerrar`, `justificar`, `historial`, permisos por rol.
- Tests de permisos (un docente no ve secciones ajenas) e idempotencia del lote.
- ✅ Colección de pruebas (archivo `.http` o `httpie`) documentada en README; tests en verde.

### Fase 3 — App: login, Mis secciones, Pase de lista, Justificar
- Pantallas 01, 02, 03, 04 **idénticas al diseño**. Cliente API con refresh automático. Cola SQLite y sincronización.
- ✅ Con el backend de la PC y el teléfono en la misma red Wi-Fi (usar la IP local en `EXPO_PUBLIC_API_URL`): login como Marisol, pasar lista de 3.º B, modo avión, marcar más alumnos, quitar modo avión → todo llega al servidor sin duplicados.

### Fase 4 — Escáner QR e Historial
- Pantalla 05 (modo sección y modo puerta) y 06. Validación offline por hash. Háptico + sonido. Linterna.
- ✅ Imprimir/mostrar en pantalla un QR de prueba (de la Fase 5 o generado con `segno` por comando) y escanearlo: presente, duplicado, inválido, otra sección.

### Fase 5 — Panel web: layout, CRUD y carnets
- Login del panel, layout con sidebar, CRUD de grados/secciones, docentes/asignaciones, cursos/horarios, estudiantes, importación Excel con vista previa, configuración y calendario.
- Carnets A4 en PDF idénticos a `panel-03-carnets-a4.html` (QR real con `segno`), regenerar/dar de baja.
- ✅ Importar un Excel de 30 alumnos con 2 filas erróneas (se reportan y no se importan), imprimir la hoja de carnets y que los QR se lean con la app.

### Fase 6 — Dashboard y reportes
- Dashboard del día y las 4 pestañas de reportes, exportes Excel (con colores) y PDF. "Recordar a los docentes" con push Expo.
- ✅ Cifras del dashboard coinciden con una consulta manual en MySQL; Excel abre bien en Excel en español.

### Fase 7 — Cierre automático, pulido y despliegue
- Comando `cerrar_dia` (marca F a los sin registrar) programado: en Windows con el Programador de tareas; en Linux con cron/systemd timer. Documentar ambos.
- Estados vacíos, errores y cargas en todas las pantallas; accesibilidad (labels, contraste, tamaño de toque).
- Despliegue: guía para VPS Ubuntu (Gunicorn + Nginx + MySQL + certbot) y build **APK con EAS** (`eas build -p android --profile preview`).
- ✅ Checklist final de la sección 12 completo.

---

## 12. Checklist final de calidad

- [ ] Las 6 pantallas móviles y las 3 del panel coinciden visualmente con `docs/diseno/` (comparar lado a lado).
- [ ] Solo Primaria visible por defecto; filtro de nivel oculto.
- [ ] Un docente nunca ve ni modifica secciones ajenas (test).
- [ ] Pase de lista y escáner funcionan en modo avión y sincronizan sin duplicar (test + prueba manual).
- [ ] Regla de hora: 7:55 = P, 7:56 = T con ingreso 7:45 y tolerancia 10 (test).
- [ ] % = (P+T+J) ÷ días hábiles, excluyendo feriados (test).
- [ ] QR sin datos personales; carnet regenerado invalida el anterior (test).
- [ ] Exportes Excel/PDF abren correctamente y respetan colores.
- [ ] Fechas y horas siempre en hora de Lima.
- [ ] `.env.example` completo, README con instalación paso a paso en Windows.
