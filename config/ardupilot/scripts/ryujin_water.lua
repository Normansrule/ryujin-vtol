-- Ryujin V21 mini: water mode (water-taxi) and the water go/no-go gate.  BENCH ONLY - NOT FLIGHT OR WATER TESTED.
--
-- ArduPilot Plane has no boat mode. Water-taxi here is MANUAL with the lift fans off (they are off in every
-- fixed-wing mode): the cruise EDF pushes (airboat) and the ruddervators steer. This script adds:
--   * a water-mode switch (RCx_OPTION = 300, Scripting1),
--   * the gate from tools/v21/water.py (same thresholds, same fail-safe rules: anything unknown is NO-GO),
--   * while in water mode: arming is refused on NO-GO, the EDF is capped to RYW_TAXI_PWM (about hull speed),
--     and a VTOL mode is refused on NO-GO (no water take-off), with the reason sent to the GCS,
--   * G8: with RC lost on the water, the EDF is held at idle.
-- Wave height has no sensor: the pilot sets RYW_WAVE_MM after looking at the water (-1 = unknown = NO-GO).
-- The leak sensor is a digital input on RYW_LEAK_PIN (-1 = not wired = NO-GO); which pin is free on the SpeedyBee
-- F405 WING is UNCONFIRMED - check the board's hwdef before wiring.
-- Every threshold is an ESTIMATE until the G7 float, leak and spray tests (see tools/v21/water.py).

local PARAM_KEY = 73
local MODE_MANUAL = 0
local SWITCH_OPTION = 300                 -- Scripting1
local EDF_FUNCTION = 70                   -- throttle (the cruise EDF)
local LOOP_MS = 200

assert(param:add_table(PARAM_KEY, "RYW_", 14), "RYW_: could not add the parameter table")
param:add_param(PARAM_KEY, 1, "ENABLE", 1)
param:add_param(PARAM_KEY, 2, "WIND_MAX", 5.0)       -- m/s, sustained (water.py MAX_WIND_M_S)
param:add_param(PARAM_KEY, 3, "WAVE_MAX", 15)        -- mm trough to crest (water.py MAX_WAVE_HEIGHT_M; G9 heel limit)
param:add_param(PARAM_KEY, 4, "BATT_MIN", 50)        -- % remaining (water.py MIN_BATTERY_PCT)
param:add_param(PARAM_KEY, 5, "WAVE_MM", -1)         -- pilot's observed wave height, mm; -1 = unknown
param:add_param(PARAM_KEY, 6, "LEAK_PIN", -1)        -- GPIO of the bilge leak sensor; -1 = not wired
param:add_param(PARAM_KEY, 7, "LEAK_ACT", 1)         -- the pin level that means "water detected"
param:add_param(PARAM_KEY, 8, "TAXI_PWM", 1450)      -- EDF PWM cap in water mode (ESTIMATE: set on the bench)
param:add_param(PARAM_KEY, 9, "STATE", 0)            -- output: 0 water mode off, 1 GO, 2 NO-GO
-- G9: analog leak sensor (preferred; the SpeedyBee F405 WING has no free digital pad with all 12 outputs in use).
-- Board ADC pins from its hwdef: 14 = PC4 (RSSI), 15 = PC5 (analog airspeed; free with an I2C airspeed sensor).
-- Wiring (ESTIMATE): 3.3 V - 100k - pin - 1M - GND, the two bilge pads across the 1M. Dry reads about 3.0 V; water
-- across the pads pulls it down; a broken wire reads about 0 V; a short to 3.3 V reads 3.3 V. Only the dry window is
-- "dry": anything else is a leak or a sensor fault, and both are NO-GO.
param:add_param(PARAM_KEY, 10, "LEAK_ANA", -1)       -- ADC pin of the analog leak sensor; -1 = not used
param:add_param(PARAM_KEY, 11, "LEAK_VLO", 2.6)      -- V, bottom of the dry window (below: water or broken wire)
param:add_param(PARAM_KEY, 12, "LEAK_VHI", 3.15)     -- V, top of the dry window (above: shorted to 3.3 V)
param:add_param(PARAM_KEY, 13, "WIND_HOLD", 60)      -- s, how long a wind reading taken sitting still stays valid

local function p(name) return param:get("RYW_" .. name) end

local function finite(x)
  return type(x) == "number" and x == x and x ~= math.huge and x ~= -math.huge
end

-- the same rules as tools/v21/water.py water_ops_allowed(); returns ok, reason
function water_ops_allowed(wind_m_s, wave_height_m, battery_pct, leak_detected)
  if leak_detected ~= false then return false, "leak sensor not reading dry" end
  if not (finite(wind_m_s) and finite(wave_height_m) and finite(battery_pct)) then return false, "input unknown" end
  if wind_m_s < 0 or wave_height_m < 0 or battery_pct < 0 or battery_pct > 100 then return false, "input out of range" end
  if wind_m_s > p("WIND_MAX") then return false, string.format("wind %.1f m/s", wind_m_s) end
  if wave_height_m > p("WAVE_MAX") / 1000 then return false, string.format("waves %.0f mm", wave_height_m * 1000) end
  if battery_pct < p("BATT_MIN") then return false, string.format("battery %.0f %%", battery_pct) end
  return true, "GO"
end

-- G9: the scripting docs mark ahrs:wind_estimate() and ahrs:airspeed_estimate() deprecated. wind_estimate() can
-- return a zero or stale vector with no sign that it is invalid (it could say "calm" in a real breeze), so the gate
-- now uses ahrs:get_wind(), which returns nil when there is no valid estimate, and ahrs:airspeed_EAS(). On firmware
-- without them it falls back to the old calls (UNCONFIRMED which release added them; check on the bench, G7 W4).
local get_wind = ahrs.get_wind and function() return ahrs:get_wind() end or function() return ahrs:wind_estimate() end
local get_aspd = ahrs.airspeed_EAS and function() return ahrs:airspeed_EAS() end or function() return ahrs:airspeed_estimate() end
local held_wind, held_ms = nil, nil

local function wind_now()
  -- on the water the aircraft weathercocks; sitting still, the airspeed sensor reads the wind. That reading is held
  -- for RYW_WIND_HOLD seconds, because the EKF often has no valid wind estimate on the water while taxiing.
  local w = get_wind()
  local best = w and math.sqrt(w:x() ^ 2 + w:y() ^ 2) or nil
  local gs = ahrs:groundspeed_vector()
  local as = get_aspd()
  local now = millis():toint()
  if as and gs and gs:length() < 0.5 then held_wind, held_ms = as, now end
  if held_ms and now - held_ms <= p("WIND_HOLD") * 1000 then best = math.max(best or 0, held_wind) end
  return best
end

local adc = nil
local adc_pin = -1
-- true = water, false = dry, nil = unknown (not wired, or a sensor fault): unknown is NO-GO in the gate
function leak_from_volts(v, lo, hi)
  if type(v) ~= "number" or v ~= v then return nil end
  if v > hi then return nil end                -- shorted to 3.3 V: a fault, not "dry"
  if v < 0.3 then return nil end               -- about 0 V: broken wire or connector off
  return v < lo
end

local function leak_now()
  local apin = math.floor(p("LEAK_ANA"))
  if apin >= 0 then
    if not adc then adc = analog:channel() end
    if not adc then return nil end
    if apin ~= adc_pin then adc:set_pin(apin); adc_pin = apin end
    return leak_from_volts(adc:voltage_average(), p("LEAK_VLO"), p("LEAK_VHI"))
  end
  local pin = math.floor(p("LEAK_PIN"))
  if pin < 0 then return nil end
  return gpio:read(pin) == (p("LEAK_ACT") ~= 0)
end

local function waves_now()
  local mm = p("WAVE_MM")
  if mm < 0 then return nil end
  return mm / 1000
end

local auth_id = arming:get_aux_auth_id()
local last_reason, last_text_ms = nil, 0
local leak_pin_set = -1

local function say(sev, msg)
  local now = millis():toint()
  if msg ~= last_reason or now - last_text_ms > 5000 then
    gcs:send_text(sev, "Ryujin water: " .. msg)
    last_reason, last_text_ms = msg, now
  end
end

local function update()
  if p("ENABLE") == 0 then return update, 1000 end
  local pin = math.floor(p("LEAK_PIN"))
  if pin >= 0 and pin ~= leak_pin_set then gpio:pinMode(pin, 0); leak_pin_set = pin end

  local sw = rc:find_channel_for_option(SWITCH_OPTION)
  local water = sw ~= nil and sw:get_aux_switch_pos() == 2
  if not water then
    param:set("RYW_STATE", 0)
    if auth_id then arming:set_aux_auth_passed(auth_id) end
    return update, LOOP_MS
  end

  local leak = leak_now()
  local ok, why = water_ops_allowed(wind_now(), waves_now(), battery:capacity_remaining_pct(0), leak)
  if leak == nil and (p("LEAK_ANA") >= 0 or p("LEAK_PIN") >= 0) then why = "leak sensor fault (check the wiring)" end
  param:set("RYW_STATE", ok and 1 or 2)
  if leak == true then say(2, "LEAK DETECTED - head for shore") end   -- 2 = critical

  if auth_id then
    if ok then arming:set_aux_auth_passed(auth_id) else arming:set_aux_auth_failed(auth_id, "water NO-GO: " .. why) end
  end

  if arming:is_armed() then
    -- no water take-off on NO-GO: a VTOL mode selected while still on the water goes back to MANUAL. Never once
    -- airborne: dropping a hover to MANUAL would stop the lift fans, so in the air it only warns.
    if not ok and quadplane:in_vtol_mode() then
      if vehicle:get_likely_flying() then
        say(2, "NO-GO in the air (" .. why .. "): land on shore")
      else
        vehicle:set_mode(MODE_MANUAL)
        say(4, "NO-GO (" .. why .. "): VTOL refused, back to MANUAL")
      end
    end
    -- taxi speed cap: the EDF never exceeds RYW_TAXI_PWM while water mode is on, on the water, not in VTOL
    -- (never in the air: capping the cruise fan in wing-borne flight would stall it)
    if not quadplane:in_vtol_mode() and not vehicle:get_likely_flying() then
      local ch = SRV_Channels:find_channel(EDF_FUNCTION)
      local cap = math.floor(p("TAXI_PWM"))
      -- G8: RC lost on the water -> EDF to idle (SERVOn_MIN), so the airboat stops instead of running on under a
      -- fixed-wing failsafe mode. rc:has_valid_input() is in the scripting docs; UNCONFIRMED on this board until W4.
      if ch and not rc:has_valid_input() then
        cap = math.floor(param:get("SERVO" .. (ch + 1) .. "_MIN") or 1000)
        say(2, "RC lost on the water: EDF idle")
      end
      if ch then
        local pwm = SRV_Channels:get_output_pwm(EDF_FUNCTION)
        if pwm and pwm > cap then SRV_Channels:set_output_pwm_chan_timeout(ch, cap, LOOP_MS + 100) end
      end
    end
  end
  if not ok then say(4, "NO-GO: " .. why) end
  return update, LOOP_MS
end

gcs:send_text(6, "Ryujin water script loaded (BENCH ONLY)")
return update, 1000
