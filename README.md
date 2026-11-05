# LatAm Campaign para DCS World

Campaña dinámica en tiempo real para DCS World, centrada en Latinoamérica entre 1990 y 2010.
La guerra corre en esta app (estilo Falcon 4.0 / BMS) y DCS muestra en 3D la parte donde estás volando.

**Estado: fase 1 (prototipo).** Hay una línea de comandos que hace cuatro cosas: crea un escuadrón
de F-5 venezolanos con matrícula, genera una misión contra un campamento de FARC/ELN en el mapa del
Cáucaso, lee en vivo lo que pasa en DCS y actualiza el desgaste de cada avión. La interfaz gráfica,
el reloj con pausa y aceleración (1×/4×/10×/64×) y el `.exe` llegan en fases siguientes
(ver el roadmap).

## Instalación (Windows)

1. Instalá [Python 3.11 o más nuevo](https://www.python.org/downloads/) y marcá
   "Add Python to PATH" durante la instalación.
2. Descargá este repositorio (botón verde **Code → Download ZIP**) y descomprimilo, o clonalo con git.
3. Abrí una terminal (PowerShell) en la carpeta del repositorio y ejecutá:

   ```powershell
   pip install -e .
   ```

No hace falta modificar `MissionScripting.lua`. El puente escribe los eventos en `dcs.log` con
`env.info`, que funciona con la instalación estándar de DCS.

## Cómo probar la fase 1

```powershell
latam init          # crea 6 F-5 (FAV-5101 a FAV-5106) en la base sustituta (Senaki-Kolkhi)
latam generate      # genera "Saved Games\DCS\Missions\LatAm - farc_f10.miz" con 2 F-5 disponibles
latam listen        # dejalo abierto mientras volás: muestra despegues, impactos y aterrizajes
```

1. Con `latam listen` abierto, en DCS andá a **Misión** y cargá `LatAm - farc_f10.miz`.
2. Despegá, atacá el campamento (waypoint "Campamento") y volvé a aterrizar en la base.
3. Salí de la misión y ejecutá `latam hangar`: el avión que volaste suma horas, pierde condición y
   queda en mantenimiento el 20 % del tiempo real de taller (1 h de vuelo → 24 min).

Otros campamentos: `latam generate --camp farc_f33` o `latam generate --camp eln_dl`.

## Qué reportar después de volar

- Si la misión carga sin errores y el F-5 sale armado (2 AIM-9, 2 Mk-82, cohetes, tanque).
- Dónde quedaron los campamentos en el mapa F10 (si alguno cayó en un lugar raro).
- La salida de `latam listen` y de `latam hangar`.
- Si algo falla, el archivo `Saved Games\DCS\Logs\dcs.log` (buscá líneas con `LATAM`).

## Estructura

```
latam_campaign/
  data/factions/       facciones (Venezuela 2005, FARC-EP, ELN) en YAML
  data/theaters/       teatros: frontera colombo-venezolana sobre el mapa del Cáucaso
  data/loadouts.yaml   armamento por modelo y tarea
  factions.py          carga y valida las facciones contra las unidades de pydcs
  hangar.py            registro de aeronaves, desgaste y mantenimiento (SQLite)
  mission/generator.py genera el .miz con pydcs
  bridge/lua/          script Lua que corre dentro de DCS y reporta eventos
  bridge/listener.py   lee dcs.log en vivo y aplica los eventos al hangar
  cli.py               comandos `latam ...`
tests/                 pruebas (incluye el script Lua corrido en Lua 5.1 con un DCS simulado)
```

## Desarrollo

```powershell
pip install -e .[dev]
pip install lupa        # opcional: para probar el script Lua
pytest
```

## Créditos y licencia

Usa [pydcs](https://github.com/pydcs/dcs) para generar misiones. Las ideas de diseño vienen de
DCS Liberation / Retribution, Foothold, Pretense y la campaña dinámica de Falcon 4.0.
Licencia LGPL-3.0-or-later, para poder reutilizar código de Liberation/Retribution.

El escenario Venezuela vs. FARC/ELN es hipotético. Los nombres de grupos y frentes son reales;
las cantidades y el equipamiento son aproximados.
