-- Ryujin V21 mini: bottom louvres / exit-vane mixer.  BENCH ONLY - NOT FLIGHT TESTED.
--
-- One servo per side drives the bottom louvres (exit vanes) of that side's front and rear lift fans (linked).
--   SERVO10 = Script1 (94) left side, SERVO12 = Script2 (95) right side.
-- Positions, from each output's own SERVOn_MIN / TRIM / MAX:
--   MIN  = shut (flush) in every fixed-wing mode: cruise, and MANUAL water-taxi (keeps spray out of the fans),
--   TRIM = open, straight down (hover),
--   TRIM -> MAX = vanes angled aft by up to RYV_RANGE degrees (pushes the aircraft forward).
-- In VTOL flight the vane angle is
--   aft bias  = RYV_FWD_MAX x (airspeed / AIRSPEED_MIN, 0..1)   - helps the transition along, fades in with speed;
--               ONLY in assisted flight / transition. G8 fix: in a pure hover (QHOVER, QLOITER) the bias pushed the
--               aircraft forward harder the faster it drifted, a positive feedback the G8 digital twin showed.
--   yaw       = RYV_YAW_MAX x yaw stick, opposite on each side   - a fore-aft force couple adds yaw authority
-- clamped to 0..RYV_RANGE (the vanes do not swing forward of straight down). Gains are ESTIMATES with no CFD or test
-- behind them: G7 bench and tethered hover tests set them. With the script stopped the outputs hold TRIM (open),
-- which is the safe position for a hover.

local PARAM_KEY = 74
local LOOP_MS = 20                       -- 50 Hz
local F_LEFT, F_RIGHT = 94, 95

assert(param:add_table(PARAM_KEY, "RYV_", 6), "RYV_: could not add the parameter table")
param:add_param(PARAM_KEY, 1, "ENABLE", 1)
param:add_param(PARAM_KEY, 2, "RANGE", 30)      -- degrees from TRIM (straight down) to MAX (full aft)
param:add_param(PARAM_KEY, 3, "FWD_MAX", 15)    -- degrees of aft bias at AIRSPEED_MIN
param:add_param(PARAM_KEY, 4, "YAW_MAX", 10)    -- degrees of differential at full yaw stick
param:add_param(PARAM_KEY, 5, "SLEW", 120)      -- degrees per second, servo rate limit

local function p(name) return param:get("RYV_" .. name) end

-- ahrs:airspeed_estimate() is deprecated in the scripting docs; prefer airspeed_EAS() where the firmware has it
local get_aspd = ahrs.airspeed_EAS and function() return ahrs:airspeed_EAS() end or function() return ahrs:airspeed_estimate() end

local function clamp(x, lo, hi) return math.max(lo, math.min(hi, x)) end

-- pure mixer (tested off-board): returns left_deg, right_deg, or nil, nil for "shut"
-- vtol: in a VTOL mode or assisted. A VTOL mode on the water (the water take-off) opens them like any hover.
-- assisted: fixed-wing flight with the lift fans helping, or a transition: the only time the aft bias applies.
function vane_mix(vtol, airspeed, aspd_min, yaw_in, assisted)
  if not vtol then return nil, nil end
  local fwd = 0
  if assisted and airspeed and aspd_min and aspd_min > 0 then fwd = p("FWD_MAX") * clamp(airspeed / aspd_min, 0, 1) end
  local yaw = p("YAW_MAX") * clamp(yaw_in or 0, -1, 1)
  local r = p("RANGE")
  return clamp(fwd + yaw, 0, r), clamp(fwd - yaw, 0, r)
end

local function servo_limits(func)
  local ch = SRV_Channels:find_channel(func)
  if not ch then return nil end
  local n = "SERVO" .. (ch + 1) .. "_"
  return {param:get(n .. "MIN"), param:get(n .. "TRIM"), param:get(n .. "MAX")}
end

-- degrees -> PWM; nil means shut
function vane_pwm(lim, deg)
  if deg == nil then return lim[1] end
  return math.floor(lim[2] + (lim[3] - lim[2]) * deg / p("RANGE") + 0.5)
end

local now_deg = {[F_LEFT] = 0, [F_RIGHT] = 0}

local function slew(func, target)
  local step = p("SLEW") * LOOP_MS / 1000
  if target == nil then now_deg[func] = nil return nil end
  local cur = now_deg[func] or 0
  cur = cur + clamp(target - cur, -step, step)
  now_deg[func] = cur
  return cur
end

local function update()
  if p("ENABLE") == 0 then return update, 500 end
  local assisted = quadplane:in_assisted_flight()
  local vtol = quadplane:in_vtol_mode() or assisted
  local yaw_ch = rc:get_channel(4)
  local l, r = vane_mix(vtol, get_aspd(), param:get("AIRSPEED_MIN"), yaw_ch and yaw_ch:norm_input() or 0, assisted)
  for func, deg in pairs({[F_LEFT] = l or false, [F_RIGHT] = r or false}) do
    local lim = servo_limits(func)
    if lim then SRV_Channels:set_output_pwm(func, vane_pwm(lim, slew(func, deg or nil))) end
  end
  return update, LOOP_MS
end

gcs:send_text(6, "Ryujin vane mixer loaded (BENCH ONLY)")
return update, 1000
