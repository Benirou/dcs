-- LatAm Campaign: puente de eventos DCS -> app.
-- Escribe cada evento como una línea "LATAM|{json}" en Saved Games\DCS\Logs\dcs.log
-- usando env.info, así NO hace falta modificar MissionScripting.lua.
-- La app lee dcs.log en vivo y actualiza el hangar y el mapa.

LatamBridge = LatamBridge or {}
LatamBridge.VERSION = "0.1.0"
LatamBridge.POSITION_INTERVAL = 15 -- segundos entre reportes de posición

local function encode(value)
  local t = type(value)
  if t == "nil" then return "null" end
  if t == "boolean" then return value and "true" or "false" end
  if t == "number" then
    if value ~= value or value == math.huge or value == -math.huge then return "null" end
    local s = string.format("%.3f", value):gsub("%.?0+$", "")
    return s
  end
  if t == "string" then
    local s = value:gsub('[%c"\\]', function(c)
      if c == '"' then return '\\"' end
      if c == "\\" then return "\\\\" end
      if c == "\n" then return "\\n" end
      return string.format("\\u%04x", string.byte(c))
    end)
    return '"' .. s .. '"'
  end
  if t == "table" then
    local parts = {}
    if #value > 0 then
      for _, v in ipairs(value) do parts[#parts + 1] = encode(v) end
      return "[" .. table.concat(parts, ",") .. "]"
    end
    for k, v in pairs(value) do
      parts[#parts + 1] = encode(tostring(k)) .. ":" .. encode(v)
    end
    return "{" .. table.concat(parts, ",") .. "}"
  end
  return "null"
end

local function emit(kind, data)
  data = data or {}
  data.kind = kind
  data.t = timer.getTime()          -- segundos desde que arrancó la misión
  data.abs = timer.getAbsTime()     -- segundos desde la medianoche del día de misión
  env.info("LATAM|" .. encode(data))
end
LatamBridge.emit = emit

local function unitInfo(obj)
  if not obj or not obj.getName then return nil end
  local ok, info = pcall(function()
    local desc = obj.getDesc and obj:getDesc() or {}
    local coal = obj.getCoalition and obj:getCoalition() or nil
    return { name = obj:getName(), type = desc.typeName, coalition = coal }
  end)
  if ok then return info end
  return nil
end

local names = {}
for name, id in pairs(world.event) do names[id] = name end

local WATCHED = {
  S_EVENT_BIRTH = "birth",
  S_EVENT_TAKEOFF = "takeoff",
  S_EVENT_LAND = "land",
  S_EVENT_HIT = "hit",
  S_EVENT_CRASH = "crash",
  S_EVENT_EJECTION = "ejection",
  S_EVENT_DEAD = "dead",
  S_EVENT_UNIT_LOST = "unit_lost",
  S_EVENT_KILL = "kill",
  S_EVENT_PILOT_DEAD = "pilot_dead",
  S_EVENT_ENGINE_SHUTDOWN = "engine_shutdown",
  S_EVENT_MISSION_END = "mission_end",
}

local handler = {}
function handler:onEvent(event)
  local kind = WATCHED[names[event.id] or ""]
  if not kind then return end
  local ok, err = pcall(function()
    local data = { initiator = unitInfo(event.initiator), target = unitInfo(event.target) }
    if event.place and event.place.getName then
      data.place = event.place:getName()
    end
    if event.weapon and event.weapon.getTypeName then
      data.weapon = event.weapon:getTypeName()
    end
    emit(kind, data)
  end)
  if not ok then env.error("LATAM bridge error: " .. tostring(err)) end
end
world.addEventHandler(handler)

-- Reporte periódico de posiciones de todas las aeronaves (para el mapa en vivo).
local function reportPositions()
  local ok, err = pcall(function()
    local list = {}
    for _, side in ipairs({ coalition.side.BLUE, coalition.side.RED }) do
      for _, cat in ipairs({ Group.Category.AIRPLANE, Group.Category.HELICOPTER }) do
        for _, group in ipairs(coalition.getGroups(side, cat) or {}) do
          for _, unit in ipairs(group:getUnits() or {}) do
            if unit and unit:isExist() then
              local p = unit:getPoint()
              local lat, lon, alt = coord.LOtoLL(p)
              list[#list + 1] = {
                name = unit:getName(), type = unit:getTypeName(), coalition = side,
                lat = lat, lon = lon, alt = alt, inAir = unit:inAir(),
              }
            end
          end
        end
      end
    end
    emit("positions", { units = list })
  end)
  if not ok then env.error("LATAM bridge positions error: " .. tostring(err)) end
  return timer.getTime() + LatamBridge.POSITION_INTERVAL
end
timer.scheduleFunction(reportPositions, nil, timer.getTime() + 5)

emit("bridge_start", { version = LatamBridge.VERSION, mission = env.mission and env.mission.date or nil })
