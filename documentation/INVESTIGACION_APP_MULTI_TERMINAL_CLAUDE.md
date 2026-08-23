# Investigación: app de escritorio para orquestar múltiples sesiones de Claude Code (macOS)

Fecha: 2026-08-23

## 0. Resumen ejecutivo (TL;DR)

1. **Antes de escribir código, mirá lo que ya existe.** La app oficial de Claude Code para escritorio
   (rediseño de abril 2026) ya trae: barra lateral con sesiones en paralelo, árbol de archivos vivo,
   terminal integrada, editor y aislamiento por git worktrees. Es prácticamente la descripción exacta
   de lo que pediste. Si el objetivo es *tenerlo*, probablo primero. Si el objetivo es *tener el tuyo*
   (control total, integración con tus bots de trading, layout propio), seguí con lo de abajo.
2. **El lenguaje no es el cuello de botella; la arquitectura de procesos sí.** Lo que hace que una app
   así sea "robusta" no es Rust vs TypeScript, es **quién es el dueño de los procesos PTY** y si las
   sesiones sobreviven a que la UI se cierre o crashee.
3. **Recomendación principal: TypeScript en todo el stack, sobre Electron**, con
   `xterm.js` (render de terminal) + `node-pty` (PTY real) + `tmux` como capa de persistencia,
   SQLite para proyectos/sesiones y Monaco para ver archivos.
4. **Alternativa fuerte si te importa el consumo de RAM: Tauri v2** (backend Rust con `portable-pty`,
   frontend React/TS con el mismo `xterm.js`). Es lo que eligió Muxara. Cuesta más aprender Rust,
   pero el binario y la memoria son ~5x menores.
5. **Descartá empezar por Swift nativo o Python.** Swift te da la mejor integración con macOS pero
   perdés todo el ecosistema web (árbol de archivos, diffs, editor) y te encerrás en una sola
   plataforma. Python no tiene un stack de UI de escritorio serio para esto.

---

## 1. Qué pediste, traducido a requisitos técnicos

| Lo que pediste | Requisito técnico real |
|---|---|
| "Algo como tmux, multiterminales de Claude" | Emulador de terminal embebido + PTY por sesión |
| "Un botón que me genere una nueva terminal ya logueada" | Spawnear `claude` heredando credenciales de `~/.claude` |
| "Ver dos al mismo tiempo / ir para atrás y ver varias" | Layout multi-panel + scrollback persistente por sesión |
| "Sesiones por proyecto, barra lateral izquierda, agregar proyecto" | Modelo de datos Proyecto → N Sesiones, persistido |
| "Ver el árbol de archivos estilo VS Code" | File watcher + árbol virtualizado + visor de archivos |
| "Robusto y estable" | Las sesiones no se mueren si la UI se cae |
| "Que funcione en la MacBook sin problemas" | Firma + notarización de Apple, soporte arm64 |

El punto **"ya logueado"** es más fácil de lo que parece: el CLI `claude` lee las credenciales de
`~/.claude` en el disco. Cualquier proceso que spawnees hereda esa sesión — no hay que hacer login
por sesión. Vos solo lanzás `claude` con el `cwd` apuntando a la carpeta del proyecto.

---

## 2. El problema real: quién es dueño de los procesos

Este es el punto que decide si la app es "robusta" o un juguete.

### Modelo A — la UI es dueña de los PTYs (ingenuo)
La app abre los procesos `claude` directamente. Si cerrás la app o crashea el render, **se mueren
todas las sesiones**. Perdés el contexto de trabajo de N agentes a la vez. Inaceptable para lo que
querés.

### Modelo B — tmux como sustrato (recomendado para el MVP)
Cada sesión de Claude vive dentro de una sesión de `tmux`. La app hace `tmux new-session -d` para
crear y se *adjunta* para mostrar. Ventajas:
- Las sesiones sobreviven a que cierres la app, e incluso a un reboot parcial.
- Podés adjuntarte desde una terminal de verdad (iTerm) si la GUI falla — vía de escape.
- Scrollback e historial los maneja tmux, no vos.
- Es exactamente lo que hacen Muxara y purplemux, y funciona.

Costo: dependencia externa (`brew install tmux`) y algo de fricción para parsear el estado del pane.

### Modelo C — daemon propio (el destino final)
Un proceso "core" headless (Rust o Node) dueño de todos los PTYs, expuesto por Unix socket. La GUI es
un cliente que se conecta y se desconecta. Te da lo mismo que tmux pero con control total del
protocolo, y habilita gratis: acceso remoto desde el celular, CLI complementaria, múltiples ventanas.

**Sugerencia:** arrancá con B, diseñá la capa de sesión detrás de una interfaz para poder pasar a C
sin reescribir la UI.

---

## 3. Comparación de stacks

### Opción 1 — Electron + TypeScript ⭐ recomendada

**Stack:** Electron + React/TS + `xterm.js` + `node-pty` + SQLite (`better-sqlite3`) + Monaco + `chokidar`.

| Pros | Contras |
|---|---|
| `node-pty` es la implementación de referencia — es la que usa VS Code | 150–250 MB de bundle |
| Todo el ecosistema de UI disponible (árbol, diffs, Monaco) sin fricción | ~200–300 MB de RAM en reposo, y sube con cada terminal abierta |
| Un solo lenguaje: TS en main, preload y renderer | Módulos nativos: `node-pty` da dolores de cabeza al recompilar para arm64 |
| Precedente directo: Crystal/Nimbalyst y purplemux hacen esto mismo | Necesitás disciplina con el proceso main para que no se trabe la UI |
| Multiplataforma gratis si algún día querés Linux/Windows | |

*Mitigación del problema de módulos nativos:* usar `@homebridge/node-pty-prebuilt-multiarch`
(API-compatible con `node-pty`, trae binarios precompilados) en vez de compilar en cada máquina.

### Opción 2 — Tauri v2 (Rust + React/TS)

**Stack:** Tauri v2 + React/TS + `xterm.js` + `portable-pty` (crate) + SQLite + Monaco.

| Pros | Contras |
|---|---|
| ~30–60 MB de RAM en reposo (aprox. 1/5 de Electron, según benchmarks de terceros) | Tenés que escribir Rust en la capa de procesos |
| Binario chico (decenas de MB) | WKWebView tiene rarezas propias vs Chromium |
| Manejo de PTY en Rust rinde mejor bajo carga (varias sesiones escupiendo output a la vez) | Ecosistema más chico; menos "copiar y pegar" |
| Sin infierno de módulos nativos de Node | Debug del puente JS↔Rust es más lento al principio |
| Ya existe `tauri-plugin-pty` para no empezar de cero | |

Muxara (Tauri + Rust + React, macOS 12+) demuestra que este camino funciona para exactamente este
caso de uso.

### Opción 3 — Swift / SwiftUI nativo

**Stack:** SwiftUI + `SwiftTerm` (emulador de terminal en Swift puro).

Mejor integración con macOS, arranque instantáneo, footprint mínimo, sin webview. Pero: solo macOS,
y perdés Monaco, los componentes de árbol de archivos y los visores de diff del mundo web — todo eso
lo tenés que construir a mano. **Solo tiene sentido si esto va a ser un producto macOS-first a largo
plazo y ya sabés Swift.**

### Opción 4 — Go + webview

Buen manejo de concurrencia para el daemon, binario único. Pero el ecosistema de UI (Wails) es más
inmaduro que Tauri y el soporte de PTY es menos pulido. **No lo recomiendo como stack principal**,
aunque Go es una opción decente si algún día querés escribir el daemon del Modelo C por separado.

### Opción 5 — Python

Descartado para la UI. No hay un toolkit de escritorio que te dé una terminal decente + árbol de
archivos + estabilidad en macOS. Python sí sirve para scripts auxiliares y para hablar con el
Agent SDK, pero no para la app.

---

## 4. Recomendación

> **TypeScript + Electron**, salvo que el consumo de recursos sea un requisito duro, en cuyo caso
> **Tauri v2 con backend en Rust**.

Razonamiento: vas a tener N terminales vivas mostrando output a alta frecuencia. Ese es justamente el
escenario donde Electron pesa. Pero el trabajo más difícil de esta app **no es el terminal** — es la
gestión de estado, la persistencia de sesiones, el árbol de archivos y el layout. Todo eso lo
resolvés más rápido y con menos bugs en TypeScript. Y si el day-1 lo resolvés con tmux como sustrato,
la parte "pesada" (mantener los procesos vivos) ni siquiera está dentro de Electron.

Regla práctica:
- **Querés algo usable en 2–3 semanas y ya sabés JS/TS →** Electron.
- **Esto va a ser un producto que corre todo el día y te molesta que coma 1 GB →** Tauri.
- En los dos casos, **el frontend es React + TypeScript + xterm.js**, así que si arrancás por
  Electron y después querés migrar a Tauri, el ~70% del código de UI se reusa.

---

## 5. Arquitectura propuesta

```
┌──────────────────────────────────────────────────────────────┐
│  Ventana (React + TypeScript)                                │
│  ┌────────────┬───────────────────────────┬───────────────┐  │
│  │  Sidebar   │   Grilla de terminales    │  Árbol de     │  │
│  │  Proyectos │   (xterm.js por sesión)   │  archivos     │  │
│  │   └ Sesión │   split / tabs / grid     │  + visor      │  │
│  └────────────┴───────────────────────────┴───────────────┘  │
└───────────────────────────┬──────────────────────────────────┘
                            │ IPC
┌───────────────────────────┴──────────────────────────────────┐
│  Proceso main / backend                                      │
│   SessionManager  →  tmux  →  PTY  →  `claude` (cwd=proyecto)│
│   ProjectStore    →  SQLite                                  │
│   FileWatcher     →  chokidar / notify                       │
│   StateReader     →  ~/.claude/projects/*.jsonl              │
└──────────────────────────────────────────────────────────────┘
```

### Piezas clave

**Crear una sesión (el "botón").**
`tmux new-session -d -s <id> -c <ruta-proyecto> 'claude'`. Nada de login: hereda `~/.claude`.
Para reanudar una sesión previa, `claude --resume <session-id>` o `claude --continue`.

**Aislamiento entre sesiones paralelas.** Si dos agentes trabajan sobre el mismo repo se van a pisar.
Usá un **git worktree por sesión** (es lo que hacen la app oficial, Conductor, Crystal y Muxara).
Es el detalle que separa una demo de algo usable en serio.

**Saber en qué anda cada sesión.** Dos caminos:
- *Frágil:* regex sobre el output del pane de tmux (así lo hace Muxara: NeedsInput / Working / Idle / Errored).
- *Sólido:* leer los logs JSONL de sesión que Claude Code escribe en `~/.claude/projects/`, que son
  estructurados. **Empezá por acá** y usá el regex solo como complemento.
- *Complementario:* el **Claude Agent SDK** (TS) te da sesiones programáticas con `resume` por
  session id y stream estructurado de mensajes. No reemplaza a la terminal interactiva, pero sirve
  para tareas de fondo, resúmenes de estado y automatizaciones sin UI.

**Árbol de archivos.** Watcher (`chokidar` en Node / `notify` en Rust) + árbol virtualizado
(`react-arborist` o similar). Cuidado con `node_modules` y `.git`: ignoralos o el watcher te come CPU.

**Persistencia.** SQLite con tablas `projects`, `sessions`, `session_events`. Guardá el `cwd`, el
worktree, el nombre de la sesión de tmux y el session id de Claude para poder reconstruir todo al
reabrir la app.

**Distribución en Mac.** Necesitás Apple Developer ID ($99/año) para firmar y notarizar; si no,
Gatekeeper la va a bloquear. Buildeá para `arm64` (y `universal` si querés soportar Intel).

---

## 6. Riesgos principales

| Riesgo | Mitigación |
|---|---|
| Módulos nativos (`node-pty`) rompen al empaquetar para arm64 | Usar builds precompilados; probar el `.dmg` empaquetado desde el día 1, no solo `npm run dev` |
| Sesiones muertas al cerrar la app | tmux (Modelo B) desde el arranque, no como "lo agrego después" |
| Agentes paralelos pisándose en el mismo repo | Un git worktree por sesión |
| RAM creciendo con 6+ terminales abiertas | Limitar scrollback en xterm.js; desmontar los terminales no visibles y rehidratar desde tmux |
| Detección de estado por regex se rompe con cada update de Claude Code | Preferir los JSONL estructurados |
| Reinventar la app oficial | Definir qué te da esto que la oficial no (ej.: integración con tus bots, layouts propios, control remoto) |

---

## 7. Roadmap sugerido

- **Semana 1 — Vertical slice.** Una ventana, un botón, una terminal. `xterm.js` + PTY + `claude`
  corriendo en el `cwd` elegido. Si esto anda, el 60% del riesgo técnico murió.
- **Semana 2 — Multi-sesión + tmux.** N sesiones, tabs/split, persistencia al reiniciar la app.
- **Semana 3 — Proyectos.** Sidebar, SQLite, agregar/quitar proyecto, sesiones agrupadas.
- **Semana 4 — Archivos.** Árbol + visor (Monaco read-only primero).
- **Semana 5 — Robustez.** Worktrees por sesión, indicadores de estado, firma y notarización.

---

## 8. Referencias

- App oficial de escritorio de Claude Code — https://code.claude.com/docs/en/desktop
- Muxara (Tauri + Rust + React + tmux, macOS) — https://github.com/muxara/muxara
- Crystal → Nimbalyst (Electron, worktrees paralelos, MIT) — https://github.com/stravu/crystal
- purplemux (multiplexer web-native para Claude Code) — https://subicura.com/purplemux/
- Claude Code UI / CloudCLI (web UI OSS) — https://github.com/siteboon/claudecodeui
- cdesktop (alternativa OSS a Claude Code Desktop) — https://github.com/cdesktop-ai/cdesktop
- `tauri-plugin-pty` — https://github.com/Tnze/tauri-plugin-pty
- Terminon (ejemplo Tauri v2 + xterm.js + portable-pty) — https://github.com/Shabari-K-S/terminon
- Agent SDK — sesiones y `resume` — https://code.claude.com/docs/en/agent-sdk/sessions
- Agent SDK TypeScript v2 (preview) — https://platform.claude.com/docs/en/agent-sdk/typescript-v2-preview
- Conductor (orquestador de agentes en macOS) — https://www.conductor.build/
