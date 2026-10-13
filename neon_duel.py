"""
NEON DUEL - duelo 1 vs 1 de motos de luz.

  Jugador 1 (CIAN)    : W A S D
  Jugador 2 (MAGENTA) : flechas
  Mantén pulsada la dirección en la que ya vas = TURBO
  P / ESC pausa  ·  F11 pantalla completa
"""
import math
import random
from array import array

import pygame

# ---------------------------------------------------------------- config
LW, LH = 320, 180            # resolución interna (pixel art, se escala)
CS = 4                       # tamaño de celda en píxeles
HUD_H = 12
GW, GH = LW // CS, (LH - HUD_H) // CS   # 80 x 42 celdas

WIN_SCORE = 3
START_INTERVAL = 0.075       # segundos por paso al empezar la ronda
MIN_INTERVAL = 0.034
ACCEL = 0.0014               # cuánto se acelera por segundo de ronda
SUDDEN_DEATH_AT = 20.0
RING_EVERY = 1.3
RING_WARN = 1.0
BOOST_COST = 3.0
BOOST_REGEN = 0.75
GHOST_TICKS = 32
BOMB_RADIUS = 5
HOLD_TO_BOOST = 0.15         # segundos manteniendo la tecla para activar turbo
MAX_POWERUPS = 3

BG = (10, 9, 20)
DOT = (30, 28, 52)
WALL = (46, 44, 78)
WALL_HI = (74, 72, 116)
TEXT = (230, 230, 245)
MUTED = (125, 122, 165)
WHITE = (255, 255, 255)
YELLOW = (255, 214, 40)
ORANGE = (255, 120, 40)
RED = (255, 50, 70)
GHOSTC = (180, 200, 255)
P1C, P1D = (0, 230, 255), (0, 58, 82)
P2C, P2D = (255, 50, 170), (82, 12, 56)

WALLV = 9
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
OPP = {"up": "down", "down": "up", "left": "right", "right": "left"}

SPRITES = {
    "boost": ["....##.", "...##..", "..##...", ".######", "...##..", "..##...", ".##...."],
    "ghost": ["..###..", ".#####.", "##.#.##", "#######", "#######", "#######", "#.#.#.#"],
    "bomb": [".....#.", "....#..", "..###..", ".#####.", ".##.##.", ".#####.", "..###.."],
}
PU_COLOR = {"boost": YELLOW, "ghost": GHOSTC, "bomb": ORANGE}


def mix(a, b, t):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def cell_center(x, y):
    return x * CS + CS / 2, HUD_H + y * CS + CS / 2


# ---------------------------------------------------------------- sonido sintetizado
class Sfx:
    def __init__(self):
        self.sounds = {}
        init = pygame.mixer.get_init()
        if not init:
            return
        self.rate, _, self.ch = init
        self.sounds = {
            "pick": self._mk(self._tone(500, 0.14, 0.25, slide=1200)),
            "beep": self._mk(self._tone(440, 0.12, 0.22)),
            "go": self._mk(self._tone(880, 0.3, 0.28)),
            "die": self._mk(self._add(self._tone(320, 0.45, 0.3, slide=-280), self._noise(0.5, 0.35))),
            "boom": self._mk(self._add(self._noise(0.4, 0.4), self._tone(90, 0.3, 0.3, slide=-50))),
            "ring": self._mk(self._tone(120, 0.22, 0.35, wave="tri", slide=-60)),
            "ghost": self._mk(self._tone(300, 0.25, 0.2, wave="tri", slide=500)),
            "select": self._mk(self._tone(660, 0.07, 0.2, slide=300)),
            "win": self._mk(sum((self._tone(f, 0.1, 0.22) for f in (523, 659, 784, 1046, 784, 1046)), [])),
        }

    def _tone(self, f, dur, vol, wave="square", slide=0.0):
        n, out, ph = int(self.rate * dur), [], 0.0
        for i in range(n):
            t = i / n
            ph += (f + slide * t) / self.rate
            v = (1.0 if ph % 1 < 0.5 else -1.0) if wave == "square" else 4 * abs(ph % 1 - 0.5) - 1
            out.append(v * vol * (1 - t) ** 2 * min(1.0, i / 80))
        return out

    def _noise(self, dur, vol):
        n = int(self.rate * dur)
        return [random.uniform(-1, 1) * vol * (1 - i / n) ** 3 for i in range(n)]

    @staticmethod
    def _add(a, b):
        if len(a) < len(b):
            a, b = b, a
        return [v + (b[i] if i < len(b) else 0) for i, v in enumerate(a)]

    def _mk(self, data):
        buf = array("h")
        for v in data:
            s = int(max(-1.0, min(1.0, v)) * 32767)
            buf.extend([s] * self.ch)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def play(self, name):
        if name in self.sounds:
            self.sounds[name].play()


# ---------------------------------------------------------------- lógica
class Player:
    def __init__(self, pid, name, color, dark, keys, label):
        self.pid, self.name, self.color, self.dark = pid, name, color, dark
        self.keys, self.label = keys, label
        self.score, self.ai = 0, False
        # paleta de la estela por antigüedad (0 = recién pintada)
        self.pal = [mix(color, WHITE, 0.55)] + [mix(dark, color, 1 - i / 15) for i in range(16)]
        self.reset(0, 0, "right")

    def reset(self, x, y, d):
        self.x, self.y, self.dir = x, y, d
        self.queue, self.alive, self.energy = [], True, 60.0
        self.ghost, self.boosting, self.want_boost = 0, False, False

    def push_dir(self, d):
        last = self.queue[-1] if self.queue else self.dir
        if d != last and d != OPP[last] and len(self.queue) < 3:
            self.queue.append(d)


class Game:
    def __init__(self, sfx, muted=False):
        self.sfx, self.muted = sfx, muted
        self.p1 = Player(1, "CIAN", P1C, P1D, {pygame.K_w: "up", pygame.K_s: "down",
                                               pygame.K_a: "left", pygame.K_d: "right"}, "WASD")
        self.p2 = Player(2, "MAGENTA", P2C, P2D, {pygame.K_UP: "up", pygame.K_DOWN: "down",
                                                  pygame.K_LEFT: "left", pygame.K_RIGHT: "right"}, "FLECHAS")
        self.players = [self.p1, self.p2]
        self.round = 0
        self.new_round()

    def snd(self, name):
        if not self.muted:
            self.sfx.play(name)

    def new_round(self):
        self.round += 1
        self.grid = [[0] * GW for _ in range(GH)]
        self.age = [[0] * GW for _ in range(GH)]
        for x in range(GW):
            self.grid[0][x] = self.grid[GH - 1][x] = WALLV
        for y in range(GH):
            self.grid[y][0] = self.grid[y][GW - 1] = WALLV
        self.tick, self.time = 0, 0.0
        self.powerups, self.next_pu = [], 1.5
        self.ring, self.next_ring, self.warn_ring, self.warn_cells = 0, SUDDEN_DEATH_AT, 0, []
        self.particles, self.popups, self.waves = [], [], []
        self.shake = self.flash = self.ring_flash = 0.0
        self.flash_col = WHITE
        off = random.choice((-3, 3))
        self.p1.reset(GW // 5, GH // 2 + off, "right")
        self.p2.reset(GW - 1 - GW // 5, GH // 2 - off, "left")
        for p in self.players:
            self.grid[p.y][p.x] = p.pid

    def interval(self):
        return max(MIN_INTERVAL, START_INTERVAL - self.time * ACCEL)

    def ring_of(self, x, y):
        return min(x, y, GW - 1 - x, GH - 1 - y)

    def can_ring(self, k):
        return GW - 2 * (k + 1) >= 16 and GH - 2 * (k + 1) >= 8

    def step(self, held):
        self.tick += 1
        self.time += self.interval()
        for p in self.players:
            if not p.alive:
                continue
            if p.ai:
                ai_think(self, p)
            if p.queue:
                p.dir = p.queue.pop(0)
            if not p.ai:
                p.want_boost = any(k in held for k, d in p.keys.items() if d == p.dir)
            p.boosting = p.want_boost and p.energy >= BOOST_COST
            if p.boosting:
                p.energy -= BOOST_COST
            else:
                p.energy = min(100.0, p.energy + BOOST_REGEN)
            if p.ghost > 0:
                p.ghost -= 1

        # el turbo da un segundo paso por tick
        for sub in (0, 1):
            movers = [p for p in self.players if p.alive and (sub == 0 or p.boosting)]
            tgt = {p.pid: (p.x + DIRS[p.dir][0], p.y + DIRS[p.dir][1]) for p in movers}
            dead = set()
            for p in movers:
                nx, ny = tgt[p.pid]
                c = self.grid[ny][nx]
                if c == WALLV or (c and p.ghost <= 0):
                    dead.add(p.pid)
            if len(movers) == 2 and tgt[1] == tgt[2]:
                dead.update((1, 2))
            for p in movers:
                if p.pid in dead:
                    self.kill(p)
                    continue
                ox, oy = cell_center(p.x, p.y)
                p.x, p.y = tgt[p.pid]
                self.grid[p.y][p.x] = p.pid
                self.age[p.y][p.x] = self.tick
                if p.boosting:
                    dx, dy = DIRS[p.dir]
                    for _ in range(2):
                        self.particles.append([ox, oy, -dx * random.uniform(30, 80) + random.uniform(-15, 15),
                                               -dy * random.uniform(30, 80) + random.uniform(-15, 15),
                                               0.3, 0.3, random.choice((YELLOW, p.color, WHITE)), 0, 1])
                self.pickup(p)

        if self.time >= self.next_pu:
            self.next_pu = self.time + random.uniform(2.0, 3.5)
            if len(self.powerups) < MAX_POWERUPS:
                self.spawn_powerup()

        k = self.ring + 1
        if self.can_ring(k):
            if self.time >= self.next_ring - RING_WARN and self.warn_ring != k:
                self.warn_ring = k
                self.warn_cells = [(x, y) for y in range(k, GH - k) for x in range(k, GW - k)
                                   if self.ring_of(x, y) == k]
            if self.time >= self.next_ring:
                self.close_ring(k)

    def close_ring(self, k):
        for x, y in self.warn_cells:
            self.grid[y][x] = WALLV
        for p in self.players:
            if p.alive and self.ring_of(p.x, p.y) <= k:
                self.kill(p)
        self.powerups = [pu for pu in self.powerups if self.ring_of(pu[0], pu[1]) > k + 1]
        self.ring, self.warn_ring, self.warn_cells = k, 0, []
        self.next_ring += RING_EVERY
        self.ring_flash = 0.5
        self.shake = max(self.shake, 0.12)
        self.snd("ring")
        if k == 1:
            self.popup(LW / 2, LH / 2, "¡MUERTE SÚBITA!", RED, 1.6)

    def kill(self, p):
        p.alive = False
        cx, cy = cell_center(p.x, p.y)
        self.burst(cx, cy, [p.color, WHITE, mix(p.color, WHITE, 0.5)], 70, 140, size=(1, 3))
        self.waves.append([cx, cy, 2, 0.5, 0.5, p.color])
        self.shake, self.flash, self.flash_col = 0.45, 0.15, p.color
        self.snd("die")

    def pickup(self, p):
        for pu in self.powerups:
            if abs(pu[0] - p.x) <= 1 and abs(pu[1] - p.y) <= 1:
                self.powerups.remove(pu)
                cx, cy = cell_center(pu[0], pu[1])
                kind = pu[2]
                if kind == "boost":
                    p.energy = 100.0
                    self.popup(cx, cy, "¡TURBO!", YELLOW)
                    self.burst(cx, cy, [YELLOW, WHITE], 26, 70)
                    self.snd("pick")
                elif kind == "ghost":
                    p.ghost = GHOST_TICKS
                    self.popup(cx, cy, "FANTASMA", GHOSTC)
                    self.burst(cx, cy, [GHOSTC, WHITE], 26, 60)
                    self.snd("ghost")
                else:
                    self.bomb(p)
                    self.popup(cx, cy, "¡BOOM!", ORANGE)
                    self.burst(cx, cy, [ORANGE, YELLOW, RED, WHITE], 60, 120, size=(1, 3))
                    self.waves.append([cx, cy, 2, 0.45, 0.45, ORANGE])
                    self.shake = max(self.shake, 0.3)
                    self.snd("boom")
                return

    def bomb(self, p):
        R = BOMB_RADIUS
        heads = {(q.x, q.y) for q in self.players if q.alive}
        for y in range(max(1, p.y - R), min(GH - 1, p.y + R + 1)):
            for x in range(max(1, p.x - R), min(GW - 1, p.x + R + 1)):
                if (x - p.x) ** 2 + (y - p.y) ** 2 <= R * R and self.grid[y][x] in (1, 2) \
                        and (x, y) not in heads:
                    self.grid[y][x] = 0

    def spawn_powerup(self):
        for _ in range(60):
            x, y = random.randint(2, GW - 3), random.randint(2, GH - 3)
            if self.grid[y][x] or self.ring_of(x, y) <= self.ring + 2:
                continue
            if any(abs(p.x - x) + abs(p.y - y) < 6 for p in self.players):
                continue
            if any(abs(pu[0] - x) + abs(pu[1] - y) < 4 for pu in self.powerups):
                continue
            kind = random.choices(("boost", "ghost", "bomb"), (45, 30, 25))[0]
            self.powerups.append([x, y, kind, self.time])
            return

    def flood(self, x, y, limit):
        seen, stack, n = {(x, y)}, [(x, y)], 0
        g = self.grid
        while stack and n < limit:
            cx, cy = stack.pop()
            n += 1
            for dx, dy in DIRS.values():
                q = (cx + dx, cy + dy)
                if q not in seen and not g[q[1]][q[0]]:
                    seen.add(q)
                    stack.append(q)
        return n

    # efectos
    def burst(self, x, y, colors, n, speed, life=(0.3, 0.9), grav=0.0, size=(1, 2)):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(0.2, 1.0) * speed
            lf = random.uniform(*life)
            self.particles.append([x, y, math.cos(a) * sp, math.sin(a) * sp, lf, lf,
                                   random.choice(colors), grav, random.randint(*size)])

    def popup(self, x, y, text, color, life=0.9):
        self.popups.append([x, y, text, color, life, life])

    def update_fx(self, dt):
        drag = max(0.0, 1 - 2.4 * dt)
        for pt in self.particles:
            pt[0] += pt[2] * dt
            pt[1] += pt[3] * dt
            pt[2] *= drag
            pt[3] = pt[3] * drag + pt[7] * dt
            pt[4] -= dt
        self.particles = [pt for pt in self.particles if pt[4] > 0]
        for pp in self.popups:
            pp[1] -= 14 * dt
            pp[4] -= dt
        self.popups = [pp for pp in self.popups if pp[4] > 0]
        for w in self.waves:
            w[2] += 160 * dt
            w[3] -= dt
        self.waves = [w for w in self.waves if w[3] > 0]
        self.shake = max(0.0, self.shake - dt)
        self.flash = max(0.0, self.flash - dt)
        self.ring_flash = max(0.0, self.ring_flash - dt)


def ai_think(g, p):
    opp = g.p2 if p is g.p1 else g.p1
    best, bs = p.dir, -1e9
    for name, (dx, dy) in DIRS.items():
        if name == OPP[p.dir]:
            continue
        nx, ny = p.x + dx, p.y + dy
        c = g.grid[ny][nx]
        if c == WALLV or (c and p.ghost <= 1):
            sc = -1e6 + random.random()
        else:
            sc = g.flood(nx, ny, 220) + (4 if name == p.dir else 0) + random.random() * 6
            if opp.alive and abs(nx - opp.x) + abs(ny - opp.y) <= 1:
                sc -= 60
            for pu in g.powerups:
                sc += 30 / (1 + abs(pu[0] - nx) + abs(pu[1] - ny))
        if sc > bs:
            bs, best = sc, name
    p.queue = [best] if best != p.dir else []
    dx, dy = DIRS[best]
    x, y, run = p.x, p.y, 0
    while run < 8:
        x, y = x + dx, y + dy
        if g.grid[y][x]:
            break
        run += 1
    p.want_boost = run >= 6 and p.energy > 35 and bs > 120


# ---------------------------------------------------------------- app / render
class App:
    def __init__(self):
        icon = pygame.Surface((32, 32))
        icon.fill(BG)
        pygame.draw.rect(icon, P1C, (4, 8, 18, 5))
        pygame.draw.rect(icon, P2C, (10, 20, 18, 5))
        pygame.display.set_icon(icon)
        self.screen = pygame.display.set_mode((LW, LH), pygame.SCALED | pygame.RESIZABLE)
        pygame.display.set_caption("NEON DUEL")
        self.canvas = pygame.Surface((LW, LH))
        self.overlay = pygame.Surface((LW, LH), pygame.SRCALPHA)
        self.clock = pygame.time.Clock()
        self.fs = pygame.font.Font(None, 14)
        self.fm = pygame.font.Font(None, 20)
        self.fb = pygame.font.Font(None, 36)
        self.fh = pygame.font.Font(None, 72)
        self.sfx = Sfx()
        self.bg = self._make_bg()
        self.sprites = {k: self._make_sprite(v, PU_COLOR[k]) for k, v in SPRITES.items()}
        self.glows = {}
        self.down = {}
        self.running, self.vs_cpu, self.t = True, False, 0.0
        self.go_title()

    def _make_bg(self):
        s = pygame.Surface((LW, LH))
        s.fill(BG)
        for y in range(0, GH, 3):
            for x in range(0, GW, 3):
                s.set_at((x * CS + 2, HUD_H + y * CS + 2), DOT)
        return s

    @staticmethod
    def _make_sprite(rows, col):
        s = pygame.Surface((7, 7), pygame.SRCALPHA)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch == "#":
                    s.set_at((x, y), col)
        return s

    def glow(self, r, col):
        key = (r, col)
        if key not in self.glows:
            s = pygame.Surface((r * 2, r * 2))
            for i in range(r, 0, -1):
                k = (1 - i / r) ** 2 * 0.55
                pygame.draw.circle(s, (int(col[0] * k), int(col[1] * k), int(col[2] * k)), (r, r), i)
            self.glows[key] = s
        return self.glows[key]

    # ---------- estados
    def go_title(self):
        self.g = Game(self.sfx, muted=True)
        self.g.p1.ai = self.g.p2.ai = True
        self.state, self.timer, self.acc, self.wait = "title", 0.0, 0.0, 0.0

    def start(self, vs_cpu):
        self.vs_cpu = vs_cpu
        self.g = Game(self.sfx)
        if vs_cpu:
            self.g.p2.ai, self.g.p2.name, self.g.p2.label = True, "CPU", "CPU"
        self.state, self.timer, self.acc, self.last_count = "countdown", 0.0, 0.0, None
        self.sfx.play("select")

    def on_key(self, k):
        st, g = self.state, self.g
        if st == "title":
            if k == pygame.K_ESCAPE:
                self.running = False
            elif k in (pygame.K_SPACE, pygame.K_RETURN):
                self.start(False)
            elif k == pygame.K_c:
                self.start(True)
        elif st == "matchend":
            if k in (pygame.K_SPACE, pygame.K_RETURN) and self.timer > 1.0:
                self.start(self.vs_cpu)
            elif k == pygame.K_ESCAPE:
                self.go_title()
        elif st == "pause":
            if k in (pygame.K_p, pygame.K_ESCAPE, pygame.K_SPACE):
                self.state = self.prev_state
            elif k == pygame.K_q:
                self.go_title()
        elif st in ("countdown", "play"):
            if k in (pygame.K_p, pygame.K_ESCAPE):
                self.prev_state, self.state = st, "pause"
                return
            for p in g.players:
                d = p.keys.get(k)
                if d and p.alive and not p.ai:
                    if st == "countdown":
                        p.dir, p.queue = d, []
                    else:
                        p.push_dir(d)

    def run_ticks(self, dt, held):
        g = self.g
        self.acc += dt
        n = 0
        while self.acc >= g.interval() and n < 4:
            self.acc -= g.interval()
            g.step(held)
            n += 1
            if sum(p.alive for p in g.players) < 2:
                self.acc = 0.0
                break
        if n == 4:
            self.acc = 0.0

    def update(self, dt, held):
        self.t += dt
        g, st = self.g, self.state
        if st == "pause":
            return
        self.timer += dt
        if st == "title":
            if sum(p.alive for p in g.players) < 2:
                self.wait += dt
                if self.wait > 1.6:
                    g.new_round()
                    self.wait = self.acc = 0.0
            else:
                self.run_ticks(dt, held)
            g.update_fx(dt)
        elif st == "countdown":
            g.update_fx(dt)
            count = 3 - int(self.timer / 0.6)
            if count != self.last_count and count > 0:
                self.sfx.play("beep")
            self.last_count = count
            if self.timer >= 1.8:
                self.state, self.timer, self.acc = "play", 0.0, 0.0
                self.sfx.play("go")
        elif st == "play":
            self.run_ticks(dt, held)
            g.update_fx(dt)
            alive = [p for p in g.players if p.alive]
            if len(alive) < 2:
                self.state, self.timer = "roundend", 0.0
                self.winner = alive[0] if alive else None
                if self.winner:
                    self.winner.score += 1
        elif st == "roundend":
            g.update_fx(dt * (0.3 if self.timer < 0.6 else 1.0))   # cámara lenta
            if self.timer > 2.6:
                if max(p.score for p in g.players) >= WIN_SCORE:
                    self.state, self.timer = "matchend", 0.0
                    self.champ = max(g.players, key=lambda p: p.score)
                    self.sfx.play("win")
                else:
                    g.new_round()
                    self.state, self.timer, self.last_count = "countdown", 0.0, None
        elif st == "matchend":
            g.update_fx(dt)
            for _ in range(2):
                lf = random.uniform(2, 3)
                g.particles.append([random.uniform(0, LW), HUD_H, random.uniform(-30, 30), random.uniform(10, 50),
                                    lf, lf, random.choice((self.champ.color, WHITE, YELLOW)), 60, 2])

    # ---------- dibujo
    def text(self, s, font, col, center=None, topleft=None, topright=None, shadow=True, alpha=255):
        img = font.render(s, False, col)
        rect = img.get_rect()
        if center:
            rect.center = (int(center[0]), int(center[1]))
        elif topleft:
            rect.topleft = topleft
        else:
            rect.topright = topright
        if shadow:
            sh = font.render(s, False, (0, 0, 0))
            sh.set_alpha(alpha)
            self.canvas.blit(sh, rect.move(1, 1))
        img.set_alpha(alpha)
        self.canvas.blit(img, rect)
        return rect

    def dim(self, a):
        self.overlay.fill((0, 0, 0, a))
        self.canvas.blit(self.overlay, (0, 0))

    def draw_arena(self):
        c, g, t = self.canvas, self.g, self.t
        c.blit(self.bg, (0, 0))
        fill = c.fill
        if g.warn_ring and int(t * 10) % 2 == 0:
            for x, y in g.warn_cells:
                fill((95, 14, 32), (x * CS, HUD_H + y * CS, CS, CS))
        for y in range(GH):
            row, arow, py = g.grid[y], g.age[y], HUD_H + y * CS
            for x in range(GW):
                v = row[x]
                if not v:
                    continue
                if v == WALLV:
                    col = WALL
                    if g.ring_flash > 0 and g.ring and g.ring_of(x, y) == g.ring:
                        col = mix(WALL, RED, g.ring_flash / 0.5)
                    fill(col, (x * CS, py, CS, CS))
                    fill(WALL_HI, (x * CS, py, CS, 1))
                else:
                    p = g.players[v - 1]
                    fill(p.pal[min(16, (g.tick - arow[x] + 2) // 3)], (x * CS, py, CS, CS))

        for x, y, kind, born in g.powerups:
            cx, cy = cell_center(x, y)
            bob = math.sin(t * 6 + x) * 1.5
            c.blit(self.glow(10, PU_COLOR[kind]), (cx - 10, cy - 10 + bob), special_flags=pygame.BLEND_RGB_ADD)
            c.blit(self.sprites[kind], (cx - 3.5, cy - 3.5 + bob))

        for p in g.players:
            if not p.alive:
                continue
            cx, cy = cell_center(p.x, p.y)
            col = mix(p.color, WHITE, 0.6)
            if p.ghost > 0 and int(t * 14) % 2:
                col = GHOSTC
            r = 14 if p.boosting else 10
            c.blit(self.glow(r, p.color), (cx - r, cy - r), special_flags=pygame.BLEND_RGB_ADD)
            fill(col, (p.x * CS - 1, HUD_H + p.y * CS - 1, CS + 2, CS + 2))

        for x, y, r, life, maxlife, col in g.waves:
            pygame.draw.circle(c, mix(BG, col, life / maxlife), (int(x), int(y)), int(r), 1)
        for pt in g.particles:
            col = mix(BG, pt[6], min(1.0, pt[4] / pt[5] * 1.6))
            fill(col, (int(pt[0]), int(pt[1]), pt[8], pt[8]))
        for x, y, s, col, life, maxlife in g.popups:
            self.text(s, self.fs, col, center=(x, y), alpha=int(255 * min(1.0, life / maxlife * 2)))

        if g.flash > 0:
            self.overlay.fill((*g.flash_col, int(90 * g.flash / 0.15)))
            c.blit(self.overlay, (0, 0))

    def draw_hud(self):
        c, g = self.canvas, self.g
        c.fill((5, 5, 12), (0, 0, LW, HUD_H))
        c.fill((30, 28, 52), (0, HUD_H - 1, LW, 1))
        if self.state == "title":
            self.text("N E O N   D U E L", self.fs, MUTED, center=(LW / 2, 6), shadow=False)
            return
        for p, left in ((g.p1, True), (g.p2, False)):
            pips = WIN_SCORE * 6
            name_img = self.fs.render(p.name, False, p.color)
            nw = name_img.get_width()
            x = 3 if left else LW - 3 - nw
            c.blit(name_img, (x, 2))
            px = x + nw + 4 if left else x - 4 - pips
            for i in range(WIN_SCORE):
                pygame.draw.rect(c, p.color if i < p.score else (45, 43, 70), (px + i * 6, 4, 4, 4))
            bx = px + pips + 3 if left else px - 45
            pygame.draw.rect(c, (45, 43, 70), (bx, 3, 42, 6), 1)
            bar_col = YELLOW if p.boosting else (RED if p.energy < BOOST_COST * 4 else p.color)
            c.fill(bar_col, (bx + 1, 4, int(40 * p.energy / 100), 4))
            if p.ghost > 0:
                c.blit(self.sprites["ghost"], (bx + 46 if left else bx - 11, 2))
        if g.ring > 0:
            if int(self.t * 4) % 2:
                self.text("MUERTE SÚBITA", self.fs, RED, center=(LW / 2, 6), shadow=False)
        else:
            self.text(f"R{g.round}  {g.time:04.1f}s", self.fs, MUTED, center=(LW / 2, 6), shadow=False)

    def draw_title(self):
        self.dim(165)
        t, cx = self.t, LW / 2
        bob = math.sin(t * 2) * 2
        n = self.fh.render("NEON", False, P1C)
        d = self.fh.render("DUEL", False, P2C)
        w = n.get_width() + 10 + d.get_width()
        x0, y0 = cx - w / 2, 18 + bob
        for img, x, sh in ((n, x0, P1D), (d, x0 + n.get_width() + 10, P2D)):
            shadow = self.fh.render("NEON" if img is n else "DUEL", False, sh)
            self.canvas.blit(shadow, (x + 3, y0 + 3))
            self.canvas.blit(img, (x, y0))
        self.text("duelo de motos de luz  ·  1 vs 1", self.fs, MUTED, center=(cx, 70))
        self.text("CIAN:  W A S D", self.fm, P1C, center=(cx - 70, 88))
        self.text("MAGENTA:  FLECHAS", self.fm, P2C, center=(cx + 70, 88))
        self.text("No choques con nada. MANTÉN la dirección en la que vas = TURBO", self.fs, TEXT,
                  center=(cx, 104))
        items = (("boost", "turbo lleno"), ("ghost", "atraviesa estelas"), ("bomb", "limpia la zona"))
        x = cx - 128
        for kind, label in items:
            self.canvas.blit(self.sprites[kind], (x, 115))
            r = self.text(label, self.fs, PU_COLOR[kind], topleft=(x + 10, 114))
            x = r.right + 18
        self.text(f"A los {int(SUDDEN_DEATH_AT)}s el muro se cierra  ·  gana quien llegue a {WIN_SCORE}",
                  self.fs, MUTED, center=(cx, 134))
        if int(t * 2.5) % 2 == 0:
            self.text("ESPACIO: 2 JUGADORES      C: VS CPU", self.fm, YELLOW, center=(cx, 152))
        self.text("ESC salir  ·  F11 pantalla completa", self.fs, MUTED, center=(cx, 170))

    def draw_countdown(self):
        g, cx, cy = self.g, LW / 2, LH / 2 + 6
        count = max(1, 3 - int(self.timer / 0.6))
        frac = (self.timer % 0.6) / 0.6
        self.text(f"RONDA {g.round}", self.fm, TEXT, center=(cx, cy - 42))
        if any(p.score == WIN_SCORE - 1 for p in g.players):
            self.text("¡PUNTO DE PARTIDO!", self.fs, RED, center=(cx, cy - 30))
        img = self.fh.render(str(count), False, mix(WHITE, YELLOW, frac))
        sc = 1.8 - 0.8 * min(1.0, frac * 4)
        img = pygame.transform.scale(img, (int(img.get_width() * sc), int(img.get_height() * sc)))
        self.canvas.blit(img, img.get_rect(center=(cx, cy + 4)))
        for p in g.players:
            hx, hy = cell_center(p.x, p.y)
            self.text(p.label, self.fs, p.color, center=(hx, hy - 10))
            dx, dy = DIRS[p.dir]
            if int(self.t * 6) % 2:
                pygame.draw.circle(self.canvas, p.color, (int(hx + dx * 8), int(hy + dy * 8)), 2)
        self.text("elige dirección inicial", self.fs, MUTED, center=(cx, cy + 36))

    def draw_band(self, h):
        cy = LH / 2 + 6
        self.overlay.fill((0, 0, 0, 0))
        self.overlay.fill((0, 0, 0, 170), (0, cy - h / 2, LW, h))
        self.canvas.blit(self.overlay, (0, 0))
        return cy

    def draw_roundend(self):
        if self.timer < 0.6:
            return
        g = self.g
        cy = self.draw_band(44)
        if self.winner:
            self.text(f"PUNTO PARA {self.winner.name}", self.fb, self.winner.color, center=(LW / 2, cy - 6))
        else:
            self.text("¡EMPATE!", self.fb, WHITE, center=(LW / 2, cy - 6))
        self.text(f"{g.p1.name} {g.p1.score}  -  {g.p2.score} {g.p2.name}", self.fs, TEXT, center=(LW / 2, cy + 14))

    def draw_matchend(self):
        cy = self.draw_band(70)
        ch = self.champ
        self.text(f"¡{ch.name} GANA!", self.fb, ch.color, center=(LW / 2, cy - 16 + math.sin(self.t * 5) * 2))
        g = self.g
        self.text(f"{g.p1.name} {g.p1.score}  -  {g.p2.score} {g.p2.name}", self.fm, TEXT, center=(LW / 2, cy + 6))
        if self.timer > 1.0 and int(self.t * 2.5) % 2 == 0:
            self.text("ESPACIO revancha  ·  ESC menú", self.fs, YELLOW, center=(LW / 2, cy + 24))

    def render(self):
        g = self.g
        self.draw_arena()
        st = self.state
        if st == "title":
            self.draw_title()
        elif st == "countdown":
            self.draw_countdown()
        elif st == "play" and g.time < 0.45:
            self.text("¡YA!", self.fh, YELLOW, center=(LW / 2, LH / 2 + 6), alpha=int(255 * (1 - g.time / 0.45)))
        elif st == "roundend":
            self.draw_roundend()
        elif st == "matchend":
            self.draw_matchend()
        elif st == "pause":
            self.dim(150)
            self.text("PAUSA", self.fb, WHITE, center=(LW / 2, LH / 2 - 4))
            self.text("ESPACIO continuar  ·  Q menú", self.fs, MUTED, center=(LW / 2, LH / 2 + 16))
        self.draw_hud()
        dx = dy = 0
        if g.shake > 0 and st != "pause":
            amp = 1 + int(g.shake * 6)
            dx, dy = random.randint(-amp, amp), random.randint(-amp, amp)
        self.screen.fill((0, 0, 0))
        self.screen.blit(self.canvas, (dx, dy))
        pygame.display.flip()

    def run(self):
        while self.running:
            dt = min(self.clock.tick(120) / 1000.0, 0.05)
            now = pygame.time.get_ticks() / 1000.0
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                elif e.type == pygame.KEYDOWN:
                    self.down[e.key] = now
                    if e.key == pygame.K_F11:
                        pygame.display.toggle_fullscreen()
                    else:
                        self.on_key(e.key)
                elif e.type == pygame.KEYUP:
                    self.down.pop(e.key, None)
                elif e.type == pygame.WINDOWFOCUSLOST:
                    self.down.clear()
                    if self.state in ("countdown", "play"):
                        self.prev_state, self.state = self.state, "pause"
            held = {k for k, t0 in self.down.items() if now - t0 >= HOLD_TO_BOOST}
            self.update(dt, held)
            self.render()


def main():
    pygame.mixer.pre_init(22050, -16, 2, 512)
    pygame.init()
    try:
        App().run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
