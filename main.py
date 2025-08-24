# main.py obstacle avoidance v5.41 
import network, socket, json
from time import ticks_ms, ticks_us, ticks_diff, sleep_us
from machine import Pin, Timer
import picobot_motors

# ------------------------
# Wi-Fi AP
# ------------------------
SSID = "picobot-oa"
PASS = "12345678"
led = Pin("LED", Pin.OUT)

ap = network.WLAN(network.AP_IF)
ap.config(essid=SSID, password=PASS)
ap.active(True)
while not ap.active():
    pass
print("AP:", ap.ifconfig())
led.on()

# ------------------------
# Motors
# ------------------------
motors = picobot_motors.MotorDriver(debug=False)

def forward(speed):
    for m in ['LeftFront','LeftBack','RightFront','RightBack']:
        motors.TurnMotor(m,'forward',speed)

def stop_all():
    motors.StopAllMotors()

def strafe_left(speed):
    motors.TurnMotor('LeftFront','backward',speed)
    motors.TurnMotor('LeftBack','forward',speed)
    motors.TurnMotor('RightFront','forward',speed)
    motors.TurnMotor('RightBack','backward',speed)

def strafe_right(speed):
    motors.TurnMotor('LeftFront','forward',speed)
    motors.TurnMotor('LeftBack','backward',speed)
    motors.TurnMotor('RightFront','backward',speed)
    motors.TurnMotor('RightBack','forward',speed)

# ------------------------
# HC-SR04 (IRQ, non-blocking)
# Trigger: GP27, Echo: GP26
# ------------------------
trig = Pin(27, Pin.OUT, value=0)
echo = Pin(26, Pin.IN)

last_distance = 999         # cm (999 = out of range / invalid)
_echo_start = 0             # ticks_us at rising edge
_awaiting_echo = False      # waiting for echo end
_echo_deadline = 0          # ticks_ms timeout

def _echo_irq(pin):
    # Single handler for both edges (faster)
    # Rising: remember start time; Falling: compute width -> distance
    global _echo_start, last_distance, _awaiting_echo
    v = pin.value()
    if v:  # rising
        _echo_start = ticks_us()
    else:  # falling
        if _awaiting_echo:
            width = ticks_diff(ticks_us(), _echo_start)  # μs
            # Convert to cm: ~58 us per cm round-trip
            d = int(width / 58)
            # Robust range filter: 2..500 cm valid, else 999
            last_distance = d if 2 <= d <= 500 else 999
            _awaiting_echo = False

# attach once
echo.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=_echo_irq)

# Timer to fire TRIG and watch timeout (no blocking loops)
_ultra_tmr = Timer()
def _ultra_tick(t):
    global _awaiting_echo, _echo_deadline, last_distance
    now = ticks_ms()
    if not _awaiting_echo:
        # Fire 10 μs pulse
        trig.off(); sleep_us(2)
        trig.on();  sleep_us(10)
        trig.off()
        _awaiting_echo = True
        _echo_deadline = now + 50  # 50 ms watchdog
    else:
        # Timeout -> mark as out of range, clear wait
        if ticks_diff(now, _echo_deadline) >= 0:
            last_distance = 999
            _awaiting_echo = False

_ultra_tmr.init(period=60, mode=Timer.PERIODIC, callback=_ultra_tick)

# ------------------------
# Mission State
# ------------------------
robot_running = False
mission_done = False
obstacles_cleared = 0
state = "IDLE"

# Tunables (defaults)
base_speed = 50           # 0..100
initial_dir = "LEFT"      # "LEFT" or "RIGHT"
strafe_time = 1300        # ms to keep strafing after line-of-sight clears
num_obstacles = 3
finish_time = 1000        # ms after last obstacle
avoid_distance = 10       # cm distance to obstacle to avoid

# ------------------------
# Avoidance state machine (lightweight, non-blocking)
# ------------------------
_state_since = ticks_ms()

def _go_state(new_state):
    global state, _state_since
    state = new_state
    _state_since = ticks_ms()

def _should_strafe_left_for_this_obstacle(idx, initdir):
    # Alternate directions each obstacle, starting with initdir
    if initdir == "LEFT":
        return (idx % 2) == 0
    else:
        return (idx % 2) == 1

_loop_tmr = Timer()
def _loop_tick(t):
    global robot_running, mission_done, obstacles_cleared
    if not robot_running or mission_done:
        stop_all()
        return

    now = ticks_ms()

    if state == "FORWARD":
        forward(base_speed)
        if last_distance < avoid_distance:  # obstacle detected
            if _should_strafe_left_for_this_obstacle(obstacles_cleared, initial_dir):
                strafe_left(base_speed)
                _go_state("STRAFE_LEFT")
            else:
                strafe_right(base_speed)
                _go_state("STRAFE_RIGHT")

    elif state == "STRAFE_LEFT":
        # Keep strafing while obstacle in front OR until grace ms expires after it clears
        strafe_left(base_speed)
        if last_distance >= avoid_distance and ticks_diff(now, _state_since) >= strafe_time:
            obstacles_cleared += 1
            if obstacles_cleared >= num_obstacles:
                forward(base_speed)
                _go_state("FINISH")
            else:
                _go_state("FORWARD")

    elif state == "STRAFE_RIGHT":
        strafe_right(base_speed)
        if last_distance >= avoid_distance and ticks_diff(now, _state_since) >= strafe_time:
            obstacles_cleared += 1
            if obstacles_cleared >= num_obstacles:
                forward(base_speed)
                _go_state("FINISH")
            else:
                _go_state("FORWARD")

    elif state == "FINISH":
        forward(base_speed)
        if ticks_diff(now, _state_since) >= finish_time:
            stop_all()
            mission_done = True
            robot_running = False

# 50 ms logic tick
_loop_tmr.init(period=50, mode=Timer.PERIODIC, callback=_loop_tick)

# ------------------------
# HTML (mobile-friendly, touch-sized)
# ------------------------
HTML = """<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PicoBot OA</title>
<style>
  :root{ --ok:#4caf50; --stop:#f44336; --done:#2196f3; --card:#fff; --bg:#f3f4f6; }
  body{ margin:0; font-family:Arial,Helvetica,sans-serif; background:var(--bg); }
  .wrap{ max-width:820px; margin:0 auto; padding:16px; }
  h1{ font-size:28px; margin:0 0 12px; text-align:center; }
  .status{ background:var(--card); border-radius:14px; padding:16px; box-shadow:0 4px 12px rgba(0,0,0,.08); margin-bottom:14px; }
  .badge{ display:inline-block; padding:6px 12px; border-radius:999px; color:#fff; font-weight:bold; font-size:16px; }
  .ok{ background:var(--ok); } .stop{ background:var(--stop);} .done{ background:var(--done); }
  .grid{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .cell{ background:#fff; border-radius:12px; padding:14px; font-size:18px; }
  .big{ font-size:24px; font-weight:bold; }
  .controls{ display:flex; gap:12px; justify-content:space-between; margin:12px 0; }
  button{ flex:1; padding:18px; font-size:22px; border:none; border-radius:12px; color:#fff; }
  .start{ background:var(--ok); } .stopbtn{ background:var(--stop); }
  .params{ background:#fff; border-radius:12px; padding:14px; box-shadow:0 4px 12px rgba(0,0,0,.08); }
  .row{ display:flex; align-items:center; justify-content:space-between; padding:10px 0; font-size:18px; }
  input, select{ font-size:20px; padding:8px 10px; width:160px; text-align:center; }
  .save{ width:100%; margin-top:8px; padding:16px; border:none; border-radius:12px; background:#000; color:#fff; font-size:20px; }
  .hint{ font-size:14px; color:#666; text-align:center; margin-top:8px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Obstacle Avoidance</h1>

  <div class="status">
    <div id="badge" class="badge stop">Stopped</div>
    <div class="grid" style="margin-top:12px;">
      <div class="cell">Distance<br><span id="dist" class="big">-</span> cm</div>
      <div class="cell">State<br><span id="st" class="big">IDLE</span></div>
      <div class="cell">Progress<br><span id="prog" class="big">0/0</span></div>
      <div class="cell">Message<br><span id="msg" class="big">Ready</span></div>
    </div>
  </div>

  <div class="controls">
    <button class="start" onclick="startRobot()">START</button>
    <button class="stopbtn" onclick="stopRobot()">STOP</button>
  </div>

  <div class="params">
    <div class="row"><span>Speed (0-100)</span><input type="number" id="speed" value="50" min="0" max="100"></div>
    <div class="row"><span>Initial direction</span>
      <select id="initdir"><option value="LEFT">LEFT</option><option value="RIGHT">RIGHT</option></select>
    </div>
    <div class="row"><span>Strafe clear (ms)</span><input type="number" id="strafe" value="1300" min="0"></div>
    <div class="row"><span># Obstacles</span><input type="number" id="numobs" value="3" min="1"></div>
    <div class="row"><span>Finish run (ms)</span><input type="number" id="finish" value="1000" min="0"></div>
    <div class="row"><span>Avoid distance (cm)</span><input type="number" id="avoid" value="10" min="2" max="500"></div>
    <button class="save" onclick="updateParams()">Update Parameters</button>
    <div class="hint">Tip: 999 cm = out of range / no echo</div>
  </div>
</div>

<script>
function qs(id){return document.getElementById(id)}
function encodeParams(obj){return Object.keys(obj).map(k=>k+"="+encodeURIComponent(obj[k])).join("&")}

function paintBadge(running, done){
  const b = qs("badge");
  if (running){ b.className="badge ok"; b.textContent="Running"; }
  else if (done){ b.className="badge done"; b.textContent="Mission Done"; }
  else { b.className="badge stop"; b.textContent="Stopped"; }
}

async function startRobot(){
  const q = encodeParams({
    action:"start",
    speed:qs("speed").value, dir:qs("initdir").value,
    strafe:qs("strafe").value, num:qs("numobs").value, finish:qs("finish").value,
    avoid:qs("avoid").value
  });
  try{
    const r = await fetch("/?"+q); const t = await r.text();
    qs("msg").textContent = t || "Started";
  }catch(e){ qs("msg").textContent = "Start failed"; }
}

async function stopRobot(){
  try{
    const r = await fetch("/?action=stop"); const t = await r.text();
    qs("msg").textContent = t || "Stopped";
    // Reset progress display
    setTimeout(() => { qs("prog").textContent = "0/0"; }, 100);
  }catch(e){ qs("msg").textContent = "Stop failed"; }
}

async function updateParams(){
  const q = encodeParams({
    action:"update",
    speed:qs("speed").value, dir:qs("initdir").value,
    strafe:qs("strafe").value, num:qs("numobs").value, finish:qs("finish").value,
    avoid:qs("avoid").value
  });
  try{
    const r = await fetch("/?"+q); const t = await r.text();
    qs("msg").textContent = t || "Settings Updated";
  }catch(e){ qs("msg").textContent = "Update failed"; }
}

async function poll(){
  try{
    const r = await fetch("/status", {cache:"no-store"});
    const data = await r.json();
    qs("dist").textContent = data.distance;
    qs("st").textContent = data.state === "FINISH" ? "Finished" : 
                          data.state === "IDLE" ? "Ready" : data.state;
    qs("prog").textContent = (data.cleared||0) + "/" + (data.total||0);
    paintBadge(data.running, data.done);
  }catch(e){
    // show a lightweight hint; avoid throwing to console repeatedly
    qs("msg").textContent = "status: offline";
  }
}
setInterval(poll, 500);
poll();
</script>
</body>
</html>
"""

# ------------------------
# HTTP server (simple, fast)
# ------------------------
def _open_socket(ip):
    addr = socket.getaddrinfo(ip, 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(2)
    return s

sock = _open_socket(ap.ifconfig()[0])
print("HTTP listening on", ap.ifconfig()[0])

def _send(client, status="200 OK", ctype="text/plain", body="OK"):
    try:
        client.send("HTTP/1.1 %s\r\nContent-Type: %s\r\nCache-Control: no-store\r\n\r\n" % (status, ctype))
        if isinstance(body, bytes):
            client.send(body)
        else:
            client.send(body)
    except:
        pass
    try:
        client.close()
    except:
        pass

def _parse_query(req_line):
    # very small query parser for GET /?... HTTP/1.1
    params = {}
    try:
        q = req_line.split(' ')[1]
        if '?' in q:
            qs = q.split('?',1)[1]
            for pair in qs.split('&'):
                if '=' in pair:
                    k,v = pair.split('=',1)
                    params[k] = v
    except:
        pass
    return params

# ------------------------
# Main service loop (non-blocking per request)
# ------------------------
while True:
    client, addr = sock.accept()
    req = client.recv(1024)
    if not req:
        client.close()
        continue
    try:
        req = req.decode()
    except:
        client.close(); continue

    # First line only
    first = req.split('\r\n',1)[0]

    # Status endpoint (fast JSON)
    if first.startswith("GET /status"):
        data = {
            "running": robot_running,
            "done": mission_done,
            "distance": last_distance,
            "state": state,
            "cleared": obstacles_cleared,
            "total": num_obstacles
        }
        _send(client, ctype="application/json", body=json.dumps(data))
        continue

    # Actions
    if first.startswith("GET /?"):
        q = _parse_query(first)

        action = q.get("action","")
        resp = "OK"

        if action == "start":
            # Update params if provided
            try:
                if "speed" in q:  base_speed = int(q["speed"])
                if "dir"   in q:  initial_dir = q["dir"].upper()
                if "strafe"in q:  strafe_time = int(q["strafe"])
                if "num"   in q:  num_obstacles = int(q["num"])
                if "finish"in q:  finish_time = int(q["finish"])
                if "avoid" in q:  avoid_distance = int(q["avoid"])
            except Exception as e:
                print("Error parsing parameters:", e)

            mission_done = False
            obstacles_cleared = 0
            _go_state("FORWARD")
            robot_running = True
            resp = "Started"

        elif action == "stop":
            robot_running = False
            mission_done = False
            obstacles_cleared = 0
            _go_state("IDLE")
            stop_all()
            resp = "Stopped"

        elif action == "update":
            try:
                if "speed" in q:  base_speed = int(q["speed"])
                if "dir"   in q:  initial_dir = q["dir"].upper()
                if "strafe"in q:  strafe_time = int(q["strafe"])
                if "num"   in q:  num_obstacles = int(q["num"])
                if "finish"in q:  finish_time = int(q["finish"])
                if "avoid" in q:  avoid_distance = int(q["avoid"])
                resp = "Settings Updated"
            except Exception as e:
                resp = "ERR - Bad Parameters"
                print("Error updating parameters:", e)

        else:
            resp = "ERR - Unknown Action"

        _send(client, ctype="text/plain", body=resp)
        continue

    # Root page
    if first.startswith("GET / "):
        _send(client, ctype="text/html", body=HTML)
        continue

    # Fallback
    _send(client, "404 Not Found", "text/plain", "Not Found")