"""
Tron Light Cycles - 3D Python Game
Requires: pip install ursina

Controls:
  A / Left Arrow  - Turn left
  D / Right Arrow - Turn right
  (you move forward automatically)
  R               - Restart
  Escape          - Quit
"""

from ursina import *
import random
import math

# ── Constants ────────────────────────────────────────────────────────────────
GRID_SIZE     = 60      # arena half-width
MOVE_SPEED    = 8       # units/sec
MOVE_INTERVAL = 0.12    # seconds between grid steps
TRAIL_WIDTH   = 0.3
TRAIL_HEIGHT  = 0.8
CYCLE_SIZE    = 0.5

# Camera offset behind/above the player
CAM_BACK  = 10
CAM_UP    = 5
CAM_LERP  = 0.12        # smoothing (0=frozen, 1=instant)

PLAYER_COLOR = color.cyan
BOT_COLORS   = [color.orange, color.lime, color.magenta]

# ── App ───────────────────────────────────────────────────────────────────────
app = Ursina(title='TRON Light Cycles', borderless=False)
window.color = color.black
window.fullscreen = False
window.exit_button.visible = False
mouse.locked = False

# ── Lighting ──────────────────────────────────────────────────────────────────
AmbientLight(color=color.rgba(15, 15, 25, 255))
sun = DirectionalLight()
sun.look_at(Vec3(0.3, -1, 0.5))

# ── Arena ─────────────────────────────────────────────────────────────────────
def build_arena():
    G = GRID_SIZE

    # Floor: near-black dark navy
    Entity(
        model='plane',
        scale=(G * 2, 1, G * 2),
        color=color.rgba(4, 6, 14, 255),
        texture=None,
    )

    # Thin grid lines just above the floor
    line_col = color.rgba(0, 55, 90, 200)
    step = 5
    for i in range(-G, G + 1, step):
        Entity(model='cube', position=Vec3(i, 0.02, 0),
               scale=(0.04, 0.02, G * 2), color=line_col)
        Entity(model='cube', position=Vec3(0, 0.02, i),
               scale=(G * 2, 0.02, 0.04), color=line_col)

    # Boundary walls - semi-transparent cyan
    wh = 3
    wt = 0.4
    wc = color.rgba(0, 200, 255, 60)
    for pos, scl in [
        (Vec3(0,  wh/2,  G), (G*2, wh, wt)),
        (Vec3(0,  wh/2, -G), (G*2, wh, wt)),
        (Vec3( G, wh/2,  0), (wt, wh, G*2)),
        (Vec3(-G, wh/2,  0), (wt, wh, G*2)),
    ]:
        Entity(model='cube', position=pos, scale=scl, color=wc)

    # Bright edge strips at base of walls so boundary is obvious
    ec = color.rgba(0, 220, 255, 255)
    ew = 0.12
    for pos, scl in [
        (Vec3(0,  ew/2,  G), (G*2, ew, ew)),
        (Vec3(0,  ew/2, -G), (G*2, ew, ew)),
        (Vec3( G, ew/2,  0), (ew, ew, G*2)),
        (Vec3(-G, ew/2,  0), (ew, ew, G*2)),
    ]:
        Entity(model='cube', position=pos, scale=scl, color=ec)

build_arena()

# ── Cycle ─────────────────────────────────────────────────────────────────────
class Cycle:
    def __init__(self, start_pos, start_angle, col, is_player=False):
        self.col         = col
        self.is_player   = is_player
        self.alive       = True
        self.angle       = float(start_angle)  # yaw degrees; 0=+Z, 90=+X
        self.pos         = Vec3(start_pos.x, CYCLE_SIZE * 0.5, start_pos.z)
        self.last_pos    = Vec3(self.pos)
        self.trail_segs  = []
        self.trail_rects = []
        self.move_timer  = 0.0
        self.pending_turn = 0

        # Body
        self.body = Entity(
            model='cube',
            color=col,
            scale=(CYCLE_SIZE * 0.9, CYCLE_SIZE * 0.5, CYCLE_SIZE * 1.6),
        )
        # Nose cone - bright white, points forward so direction is obvious
        self.nose = Entity(
            model='cube',
            color=color.white,
            scale=(CYCLE_SIZE * 0.4, CYCLE_SIZE * 0.25, CYCLE_SIZE * 0.5),
        )
        # Top glow stripe
        self.stripe = Entity(
            model='cube',
            color=col,
            scale=(CYCLE_SIZE * 0.92, CYCLE_SIZE * 0.08, CYCLE_SIZE * 1.62),
        )
        # Wheels
        wc = color.rgba(15, 15, 15, 255)
        self.wl = Entity(model='cube', color=wc,
                         scale=(0.1, CYCLE_SIZE * 0.9, CYCLE_SIZE * 1.3))
        self.wr = Entity(model='cube', color=wc,
                         scale=(0.1, CYCLE_SIZE * 0.9, CYCLE_SIZE * 1.3))

        self._sync_mesh()

    def dir_vec(self):
        rad = math.radians(self.angle)
        return Vec3(math.sin(rad), 0, math.cos(rad))

    def _yaw(self):
        d = self.dir_vec()
        return -math.degrees(math.atan2(d.x, d.z))

    def _sync_mesh(self):
        p  = self.pos
        ry = self._yaw()
        d  = self.dir_vec()
        right = Vec3(d.z, 0, -d.x)

        self.body.position   = p
        self.body.rotation_y = ry

        self.nose.position   = p + d * (CYCLE_SIZE * 0.9) + Vec3(0, -CYCLE_SIZE * 0.05, 0)
        self.nose.rotation_y = ry

        self.stripe.position   = p + Vec3(0, CYCLE_SIZE * 0.29, 0)
        self.stripe.rotation_y = ry

        self.wl.position   = p - right * CYCLE_SIZE * 0.52
        self.wl.rotation_y = ry
        self.wr.position   = p + right * CYCLE_SIZE * 0.52
        self.wr.rotation_y = ry

    def _add_trail(self, from_p, to_p):
        dx = to_p.x - from_p.x
        dz = to_p.z - from_p.z
        length = math.sqrt(dx*dx + dz*dz)
        if length < 0.01:
            return
        mid = (from_p + to_p) * 0.5
        ang = -math.degrees(math.atan2(dx, dz))

        seg = Entity(
            model='cube',
            position=Vec3(mid.x, TRAIL_HEIGHT * 0.5, mid.z),
            scale=(TRAIL_WIDTH, TRAIL_HEIGHT, length),
            rotation_y=ang,
            color=self.col,
        )
        self.trail_segs.append(seg)

        ca = abs(math.cos(math.radians(ang)))
        sa = abs(math.sin(math.radians(ang)))
        hw = TRAIL_WIDTH / 2
        hd = length / 2
        self.trail_rects.append((mid.x, mid.z,
                                  hw * ca + hd * sa,
                                  hw * sa + hd * ca))

    def update(self, dt):
        if not self.alive:
            return
        self.move_timer += dt
        if self.move_timer >= MOVE_INTERVAL:
            self.move_timer -= MOVE_INTERVAL
            if self.pending_turn:
                self.angle = (self.angle + self.pending_turn * 90) % 360
                self.pending_turn = 0
            new_pos = self.pos + self.dir_vec() * (MOVE_SPEED * MOVE_INTERVAL)
            self._add_trail(self.last_pos, new_pos)
            self.last_pos = Vec3(new_pos)
            self.pos = new_pos
            self._sync_mesh()

    def turn(self, d):
        if self.alive:
            self.pending_turn = d

    def check_death(self, all_cycles):
        if not self.alive:
            return
        x, z = self.pos.x, self.pos.z
        if abs(x) >= GRID_SIZE - 1 or abs(z) >= GRID_SIZE - 1:
            self._die()
            return
        for cyc in all_cycles:
            own      = cyc is self
            skip_end = 3 if own else 0
            rects    = cyc.trail_rects
            for i, (sx, sz, hw, hd) in enumerate(rects):
                if own and i >= len(rects) - skip_end:
                    continue
                if abs(x - sx) < hw + 0.35 and abs(z - sz) < hd + 0.35:
                    self._die()
                    return

    def _die(self):
        self.alive = False
        grey = color.rgba(70, 70, 70, 200)
        self.body.color   = grey
        self.stripe.color = grey
        self.nose.color   = grey
        for _ in range(8):
            e = Entity(
                model='sphere',
                scale=random.uniform(0.2, 0.9),
                position=self.pos + Vec3(
                    random.uniform(-1.5, 1.5),
                    random.uniform(0, 2),
                    random.uniform(-1.5, 1.5)
                ),
                color=self.col,
            )
            destroy(e, delay=0.5)

    def destroy_all(self):
        for e in (self.body, self.nose, self.stripe, self.wl, self.wr):
            destroy(e)
        for s in self.trail_segs:
            destroy(s)
        self.trail_segs.clear()
        self.trail_rects.clear()


# ── Bot AI ────────────────────────────────────────────────────────────────────
class Bot:
    def __init__(self, cycle):
        self.cycle          = cycle
        self.think_timer    = 0.0
        self.think_interval = random.uniform(0.1, 0.22)

    def update(self, dt, all_cycles):
        c = self.cycle
        if not c.alive:
            return
        self.think_timer += dt
        if self.think_timer < self.think_interval:
            return
        self.think_timer = 0.0

        if self._safe(c, 0, 5, all_cycles) and random.random() > 0.12:
            return
        opts = [-1, 1]
        random.shuffle(opts)
        for t in opts:
            if self._safe(c, t, 5, all_cycles):
                c.turn(t)
                return
        c.turn(random.choice([-1, 1]))

    def _safe(self, c, turn, steps, all_cycles):
        ang = (c.angle + turn * 90) % 360
        rad = math.radians(ang)
        dx, dz = math.sin(rad), math.cos(rad)
        x, z   = c.pos.x, c.pos.z
        step   = MOVE_SPEED * MOVE_INTERVAL
        for _ in range(steps):
            x += dx * step
            z += dz * step
            if abs(x) >= GRID_SIZE - 2 or abs(z) >= GRID_SIZE - 2:
                return False
            for cyc in all_cycles:
                for sx, sz, hw, hd in cyc.trail_rects:
                    if abs(x - sx) < hw + 0.4 and abs(z - sz) < hd + 0.4:
                        return False
        return True


# ── Camera ────────────────────────────────────────────────────────────────────
camera.position = Vec3(0, CAM_UP, -CAM_BACK)
camera.rotation = Vec3(18, 0, 0)

_cam_yaw = 0.0

def follow_camera(player):
    global _cam_yaw
    if not player.alive:
        return

    # Camera yaw = player facing direction (camera looks the same way player moves)
    target_yaw = player.angle

    # Lerp via shortest arc to avoid spinning the wrong way
    diff = (target_yaw - _cam_yaw + 180) % 360 - 180
    _cam_yaw += diff * 0.18

    # Position: directly behind the player (opposite of facing direction)
    rad = math.radians(_cam_yaw)
    behind = Vec3(-math.sin(rad) * CAM_BACK, 0, -math.cos(rad) * CAM_BACK)

    target_pos = player.pos + behind + Vec3(0, CAM_UP, 0)
    camera.position = lerp(camera.position, target_pos, CAM_LERP)

    # Rotation: camera yaw matches player so we look forward, tilt down slightly
    camera.rotation_y = _cam_yaw
    camera.rotation_x = 18


# ── HUD ───────────────────────────────────────────────────────────────────────
hud_score = Text('SCORE: 0',           position=(-0.84, 0.47), scale=1.1,
                 color=color.cyan,     origin=(-0.5, 0.5))
hud_bots  = Text('OPPONENTS: ● ● ●',  position=(-0.84, 0.42), scale=0.95,
                 color=color.orange,   origin=(-0.5, 0.5))
hud_title = Text('TRON\nLIGHT CYCLES', position=(0, 0.12),    scale=3,
                 color=color.cyan,     origin=(0, 0))
hud_msg   = Text('Press R to start',   position=(0, -0.02),    scale=1.3,
                 color=color.white,    origin=(0, 0))
Text('A / ← = Turn Left    D / → = Turn Right    R = Restart    Esc = Quit',
     position=(0, -0.47), scale=0.85,
     color=color.rgba(120, 190, 210, 180), origin=(0, 0.5))

def update_hud(g):
    g.score = sum(1 for c in g.cycles[1:] if not c.alive) * 100
    hud_score.text = f'SCORE: {g.score}'
    hud_bots.text  = 'OPPONENTS: ' + ' '.join(
        '●' if c.alive else '○' for c in g.cycles[1:])


# ── Game state ────────────────────────────────────────────────────────────────
class GameState:
    def __init__(self):
        self.cycles  = []
        self.bots    = []
        self.player  = None
        self.score   = 0
        self.running = False

    def start(self):
        for c in self.cycles:
            c.destroy_all()
        self.cycles.clear()
        self.bots.clear()
        self.score   = 0
        self.running = True
        hud_title.text = ''
        hud_msg.text   = ''

        spawns = [
            (Vec3( 0,  0,  25), 180),
            (Vec3(-22, 0, -22),   0),
            (Vec3( 22, 0, -22),   0),
            (Vec3(  0, 0, -30),  90),
        ]
        self.player = Cycle(spawns[0][0], spawns[0][1], PLAYER_COLOR, is_player=True)
        self.cycles.append(self.player)
        for i in range(3):
            c = Cycle(spawns[i+1][0], spawns[i+1][1], BOT_COLORS[i])
            self.cycles.append(c)
            self.bots.append(Bot(c))

        update_hud(self)

    def end(self, won):
        self.running = False
        if won:
            hud_title.text  = '[VICTORY]'
            hud_title.color = color.cyan
        else:
            hud_title.text  = '[DEREZZED]'
            hud_title.color = color.orange
        hud_msg.text = f'Score: {self.score}      Press R to play again'


gs = GameState()


# ── Main loop ─────────────────────────────────────────────────────────────────
def update():
    if not gs.running:
        return
    dt = time.dt

    for c in gs.cycles:
        c.update(dt)
    for b in gs.bots:
        b.update(dt, gs.cycles)
    for c in gs.cycles:
        c.check_death(gs.cycles)

    update_hud(gs)
    follow_camera(gs.player)

    if not gs.player.alive:
        gs.end(False)
    elif all(not c.alive for c in gs.cycles[1:]):
        gs.end(True)


def input(key):
    if key == 'escape':
        application.quit()
    if key == 'r':
        gs.start()
    if gs.running:
        if key in ('a', 'left arrow'):
            gs.player.turn(-1)
        if key in ('d', 'right arrow'):
            gs.player.turn(1)


app.run()
