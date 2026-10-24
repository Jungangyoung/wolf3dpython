"""
WOLFENSTEIN ASCII: PLAYABLE EDITION
Runs in Thonny with Python's standard library only (Tkinter).

Controls:
  W / S       Move forward / backward
  A / D       Strafe left / right
  LEFT / RIGHT Turn
  SPACE       Shoot (hold to fire)
  ESC         Pause / resume
  N           New randomly generated dungeon
  Q           Quit
Walk over + medkits and $ ammo boxes to collect them.
"""
import math
import random
import tkinter as tk
from collections import deque

# ---------- Configuration ----------
WINDOW_W, WINDOW_H = 1100, 720
VIEW_W, VIEW_H = 800, 620
MAP_W, MAP_H = 39, 25
FOV = math.pi / 3
MAX_DEPTH = 22.0
PLAYER_SPEED = 3.0
TURN_SPEED = 2.25
ENEMY_COUNT = 12
START_HP = 100
START_AMMO = 42
MAX_AMMO = 60
FIRE_DELAY = 0.28
RAY_STEP = 0.045
FPS_MS = 30

ENEMY_STATS = {
    "hunter":  {"hp": 2, "speed": 1.00, "color": "#e65b4f", "damage": (4, 7)},
    "flanker": {"hp": 2, "speed": 0.90, "color": "#f0a33a", "damage": (3, 6)},
    "guard":   {"hp": 3, "speed": 0.60, "color": "#65b8f4", "damage": (3, 6)},
    "brute":   {"hp": 5, "speed": 0.48, "color": "#c04fe0", "damage": (7, 11)},
    "scout":   {"hp": 1, "speed": 1.35, "color": "#e9e65a", "damage": (2, 4)},
    "sniper":  {"hp": 2, "speed": 0.52, "color": "#f5f5f5", "damage": (5, 9)},
}
PICKUP_COLORS = {"medkit": "#65e572", "ammo": "#f4d34f"}


def angle_diff(a, b):
    return (a - b + math.pi) % (2 * math.pi) - math.pi


class Wolf3D:
    def __init__(self, root):
        self.root = root
        self.root.title("Wolfenstein ASCII — Playable Edition")
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.root.minsize(960, 650)
        self.canvas = tk.Canvas(root, width=WINDOW_W, height=WINDOW_H,
                                bg="#111318", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.keys = set()
        self.paused = False
        self.game_over = False
        self.victory = False
        self.frame = 0
        self.last_time = None
        self.fire_timer = 0.0
        self.flash_timer = 0.0
        self.message = "Find enemies. Collect supplies. Stay alive!"
        self.reset()
        root.bind("<KeyPress>", self.key_down)
        root.bind("<KeyRelease>", self.key_up)
        root.bind("<FocusOut>", lambda _e: self.keys.clear())
        self.tick()

    def key_down(self, event):
        key = event.keysym.lower()
        if key in ("escape",):
            self.paused = not self.paused
            self.keys.clear()
        elif key == "n":
            self.reset()
        elif key == "q":
            self.root.destroy()
        else:
            self.keys.add(key)

    def key_up(self, event):
        self.keys.discard(event.keysym.lower())

    def generate_dungeon(self):
        grid = [['#'] * MAP_W for _ in range(MAP_H)]
        rooms = []
        attempts = 0
        while len(rooms) < 11 and attempts < 500:
            attempts += 1
            w, h = random.randint(4, 8), random.randint(4, 7)
            x = random.randint(1, MAP_W - w - 2)
            y = random.randint(1, MAP_H - h - 2)
            if any(x <= rx + rw and x + w >= rx and y <= ry + rh and y + h >= ry
                   for rx, ry, rw, rh in rooms):
                continue
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    grid[yy][xx] = '.'
            if rooms:
                px, py, pw, ph = rooms[-1]
                ax, ay = px + pw // 2, py + ph // 2
                bx, by = x + w // 2, y + h // 2
                if random.choice((True, False)):
                    for xx in range(min(ax, bx), max(ax, bx) + 1):
                        grid[ay][xx] = '.'
                    for yy in range(min(ay, by), max(ay, by) + 1):
                        grid[yy][bx] = '.'
                else:
                    for yy in range(min(ay, by), max(ay, by) + 1):
                        grid[yy][ax] = '.'
                    for xx in range(min(ax, bx), max(ax, bx) + 1):
                        grid[by][xx] = '.'
            rooms.append((x, y, w, h))
        return grid, rooms

    def is_wall(self, x, y):
        ix, iy = int(x), int(y)
        return not (0 <= ix < MAP_W and 0 <= iy < MAP_H) or self.world[iy][ix] == '#'

    def move_entity(self, entity, dx, dy, radius=0.18):
        nx = entity["x"] + dx
        if not self.is_wall(nx + radius, entity["y"]) and not self.is_wall(nx - radius, entity["y"]):
            entity["x"] = nx
        ny = entity["y"] + dy
        if not self.is_wall(entity["x"], ny + radius) and not self.is_wall(entity["x"], ny - radius):
            entity["y"] = ny

    def clear_shot(self, x1, y1, x2, y2):
        dist = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(dist / 0.12))
        for i in range(1, steps):
            t = i / steps
            if self.is_wall(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t):
                return False
        return True

    def reset(self):
        self.world, self.rooms = self.generate_dungeon()
        sx, sy, sw, sh = self.rooms[0]
        self.player = {"x": sx + sw / 2, "y": sy + sh / 2,
                       "angle": random.uniform(-math.pi, math.pi),
                       "hp": START_HP, "ammo": START_AMMO}
        floors = [(x, y) for y in range(1, MAP_H - 1)
                  for x in range(1, MAP_W - 1)
                  if self.world[y][x] == "." and
                  math.hypot(x + 0.5 - self.player["x"],
                             y + 0.5 - self.player["y"]) > 7]
        random.shuffle(floors)
        self.enemies = []
        used = set()
        for x, y in floors:
            if len(self.enemies) >= ENEMY_COUNT:
                break
            if (x, y) in used:
                continue
            mode = random.choices(
                ["hunter", "flanker", "guard", "brute", "scout", "sniper"],
                weights=[3, 2, 2, 1, 2, 1])[0]
            stats = ENEMY_STATS[mode]
            self.enemies.append({
                "x": x + 0.5, "y": y + 0.5, "mode": mode,
                "hp": stats["hp"], "alive": True,
                "attack": random.uniform(0.3, 1.2),
                "strafe": random.choice((-1, 1)), "wander": random.uniform(0, 2)
            })
            used.add((x, y))
        random.shuffle(floors)
        self.pickups = []
        for i, (x, y) in enumerate(floors):
            if len(self.pickups) >= 8:
                break
            if any(math.hypot(x + .5 - e["x"], y + .5 - e["y"]) < 1.0
                   for e in self.enemies):
                continue
            kind = "medkit" if sum(p["kind"] == "medkit" for p in self.pickups) < 3 else "ammo"
            self.pickups.append({"x": x + .5, "y": y + .5, "kind": kind, "active": True})
        self.score = 0
        self.shots = 0
        self.kills = 0
        self.fire_timer = 0
        self.flash_timer = 0
        self.paused = False
        self.game_over = False
        self.victory = False
        self.message = "New dungeon! WASD move, arrows turn, SPACE shoots."
        self.keys.clear()
        self.nav_timer = 0
        self.nav_distance = {}
        self.nav_next = {}
        self.build_navigation()

    def build_navigation(self):
        # One breadth-first search from the player's tile gives every enemy
        # a shared route toward the player, instead of running BFS per enemy.
        goal = (int(self.player["x"]), int(self.player["y"]))
        dist = {goal: 0}
        nxt = {}
        queue = deque([goal])
        while queue:
            x, y = queue.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                tile = (x + dx, y + dy)
                if tile in dist or self.is_wall(tile[0] + .5, tile[1] + .5):
                    continue
                dist[tile] = dist[(x, y)] + 1
                nxt[tile] = (x, y)
                queue.append(tile)
        self.nav_distance = dist
        self.nav_next = nxt

    def update(self, dt):
        if self.paused or self.game_over or self.victory:
            return
        p = self.player
        self.fire_timer = max(0, self.fire_timer - dt)
        self.flash_timer = max(0, self.flash_timer - dt)
        turn = 0
        if "left" in self.keys:
            turn -= 1
        if "right" in self.keys:
            turn += 1
        p["angle"] += turn * TURN_SPEED * dt

        forward = (("w" in self.keys) or ("up" in self.keys)) - (("s" in self.keys) or ("down" in self.keys))
        strafe = ("d" in self.keys) - ("a" in self.keys)
        # Normalize diagonal movement so it isn't faster.
        length = math.hypot(forward, strafe)
        if length:
            forward /= length
            strafe /= length
            dx = (math.cos(p["angle"]) * forward + math.cos(p["angle"] + math.pi / 2) * strafe) * PLAYER_SPEED * dt
            dy = (math.sin(p["angle"]) * forward + math.sin(p["angle"] + math.pi / 2) * strafe) * PLAYER_SPEED * dt
            old_tile = (int(p["x"]), int(p["y"]))
            self.move_entity(p, dx, dy)
            if (int(p["x"]), int(p["y"])) != old_tile:
                self.nav_timer = 0

        self.nav_timer -= dt
        if self.nav_timer <= 0:
            self.build_navigation()
            self.nav_timer = 0.22

        # Collect supplies automatically by walking close.
        for item in self.pickups:
            if not item["active"]:
                continue
            if math.hypot(item["x"] - p["x"], item["y"] - p["y"]) < .55:
                if item["kind"] == "medkit" and p["hp"] < START_HP:
                    amount = min(30, START_HP - p["hp"])
                    p["hp"] += amount
                    item["active"] = False
                    self.message = f"MEDKIT: +{amount} HP"
                elif item["kind"] == "ammo" and p["ammo"] < MAX_AMMO:
                    amount = min(15, MAX_AMMO - p["ammo"])
                    p["ammo"] += amount
                    item["active"] = False
                    self.message = f"AMMO BOX: +{amount} rounds"

        # Enemies: moderate aggression, role-specific behavior.
        for e in self.enemies:
            if not e["alive"]:
                continue
            dx, dy = p["x"] - e["x"], p["y"] - e["y"]
            dist = max(.001, math.hypot(dx, dy))
            los = self.clear_shot(e["x"], e["y"], p["x"], p["y"])
            e["attack"] += dt
            mode = e["mode"]
            stats = ENEMY_STATS[mode]

            if dist < 1.0:
                cooldown = 1.0 if mode == "brute" else 1.35
                if e["attack"] >= cooldown:
                    e["attack"] = 0
                    damage = random.randint(*stats["damage"])
                    p["hp"] = max(0, p["hp"] - damage)
                    self.message = f"{mode.upper()} hits you for {damage}!"
                continue

            if mode in ("guard", "sniper") and los and dist < (7 if mode == "guard" else 10) and dist > 2.2:
                cooldown = 2.3 if mode == "guard" else 1.8
                if e["attack"] >= cooldown:
                    e["attack"] = 0
                    damage = random.randint(*stats["damage"])
                    p["hp"] = max(0, p["hp"] - damage)
                    self.message = f"{mode.upper()} shoots you for {damage}!"
                if dist < 3:
                    self.move_entity(e, -dx / dist * stats["speed"] * dt,
                                     -dy / dist * stats["speed"] * dt)
                continue

            tile = (int(e["x"]), int(e["y"]))
            next_tile = self.nav_next.get(tile)
            if next_tile is not None:
                vx, vy = next_tile[0] + .5 - e["x"], next_tile[1] + .5 - e["y"]
            else:
                vx, vy = dx, dy
            norm = max(.001, math.hypot(vx, vy))
            speed = stats["speed"]
            if mode == "flanker" and dist < 4:
                e["wander"] += dt
                side = e["strafe"]
                vx += (-dy / dist) * side * 1.1
                vy += (dx / dist) * side * 1.1
            self.move_entity(e, vx / norm * speed * dt, vy / norm * speed * dt)

        if "space" in self.keys and self.fire_timer <= 0:
            self.fire_weapon()

        if p["hp"] <= 0:
            self.game_over = True
            self.message = "YOU DIED — press N for a new dungeon."
        elif not any(e["alive"] for e in self.enemies):
            self.victory = True
            self.message = "DUNGEON CLEARED! Press N for another dungeon."

    def fire_weapon(self):
        p = self.player
        self.fire_timer = FIRE_DELAY
        if p["ammo"] <= 0:
            self.message = "OUT OF AMMO — find a $ ammo box!"
            return
        p["ammo"] -= 1
        self.shots += 1
        self.flash_timer = .08
        # Hitscan weapon: target must be close to the crosshair and visible.
        candidates = []
        for e in self.enemies:
            if not e["alive"]:
                continue
            dx, dy = e["x"] - p["x"], e["y"] - p["y"]
            dist = math.hypot(dx, dy)
            rel = angle_diff(math.atan2(dy, dx), p["angle"])
            if abs(rel) < .13 and dist < 9 and self.clear_shot(p["x"], p["y"], e["x"], e["y"]):
                candidates.append((dist, e))
        if not candidates:
            self.message = "SHOT MISSED — line up the crosshair."
            return
        _, target = min(candidates, key=lambda pair: pair[0])
        target["hp"] -= 1
        self.message = f"HIT {target['mode'].upper()}!"
        if target["hp"] <= 0:
            target["alive"] = False
            self.kills += 1
            self.score += 100
            self.message = f"{target['mode'].upper()} DEFEATED! +100"

    def cast_ray(self, angle):
        """Fast grid DDA raycast: checks crossed grid cells instead of tiny steps."""
        px, py = self.player["x"], self.player["y"]
        rx, ry = math.cos(angle), math.sin(angle)
        map_x, map_y = int(px), int(py)
        delta_x = abs(1.0 / rx) if abs(rx) > 1e-12 else float("inf")
        delta_y = abs(1.0 / ry) if abs(ry) > 1e-12 else float("inf")

        if rx < 0:
            step_x = -1
            side_x = (px - map_x) * delta_x
        else:
            step_x = 1
            side_x = (map_x + 1.0 - px) * delta_x
        if ry < 0:
            step_y = -1
            side_y = (py - map_y) * delta_y
        else:
            step_y = 1
            side_y = (map_y + 1.0 - py) * delta_y

        dist = 0.0
        while dist < MAX_DEPTH:
            if side_x < side_y:
                map_x += step_x
                dist = side_x
                side_x += delta_x
            else:
                map_y += step_y
                dist = side_y
                side_y += delta_y
            if not (0 <= map_x < MAP_W and 0 <= map_y < MAP_H):
                break
            if self.world[map_y][map_x] == "#":
                return max(.02, dist), px + rx * dist, py + ry * dist
        return MAX_DEPTH, px + rx * MAX_DEPTH, py + ry * MAX_DEPTH

    def draw(self):
        c = self.canvas
        c.delete("all")
        # Scene background / floor and ceiling.
        c.create_rectangle(0, 0, VIEW_W, VIEW_H // 2, fill="#151a27", outline="")
        c.create_rectangle(0, VIEW_H // 2, VIEW_W, VIEW_H, fill="#29251f", outline="")
        zbuffer = [MAX_DEPTH] * VIEW_W
        # Cast one ray per 2 pixels for a smooth-enough view on older PCs.
        strip = 2
        for x in range(0, VIEW_W, strip):
            angle = self.player["angle"] + (x / VIEW_W - .5) * FOV
            dist, hitx, hity = self.cast_ray(angle)
            corrected = max(.08, dist * math.cos(angle - self.player["angle"]))
            zbuffer[x] = corrected
            if x + 1 < VIEW_W:
                zbuffer[x + 1] = corrected
            wall_h = min(VIEW_H, int(VIEW_H / corrected))
            top = VIEW_H // 2 - wall_h // 2
            shade = max(35, min(220, int(205 / (1 + corrected * .22))))
            # Different wall faces get slightly different brightness.
            face = int(hitx * 7 + hity * 5) % 2
            shade = max(28, min(220, shade - (20 if face else 0)))
            color = f"#{shade:02x}{int(shade*.88):02x}{int(shade*.72):02x}"
            c.create_rectangle(x, top, x + strip + 1, top + wall_h,
                               fill=color, outline=color)
        # Draw pickups and enemies back-to-front, with z-buffer occlusion.
        sprites = []
        for item in self.pickups:
            if item["active"]:
                dx, dy = item["x"] - self.player["x"], item["y"] - self.player["y"]
                dist = math.hypot(dx, dy)
                rel = angle_diff(math.atan2(dy, dx), self.player["angle"])
                if abs(rel) < FOV / 2 + .08:
                    sprites.append((dist, rel, "pickup", item))
        for e in self.enemies:
            if e["alive"]:
                dx, dy = e["x"] - self.player["x"], e["y"] - self.player["y"]
                dist = math.hypot(dx, dy)
                rel = angle_diff(math.atan2(dy, dx), self.player["angle"])
                if abs(rel) < FOV / 2 + .10:
                    sprites.append((dist, rel, "enemy", e))
        sprites.sort(key=lambda s: s[0], reverse=True)
        for dist, rel, kind, obj in sprites:
            corrected = max(.1, dist * math.cos(rel))
            sx = int((.5 + rel / FOV) * VIEW_W)
            if not 0 <= sx < VIEW_W:
                continue
            if corrected > zbuffer[max(0, min(VIEW_W - 1, sx))] + .25:
                continue
            size = max(4, min(VIEW_H * 1.2, VIEW_H / corrected))
            if kind == "pickup":
                col = PICKUP_COLORS[obj["kind"]]
                y = VIEW_H // 2 + size * .20
                c.create_rectangle(sx-size*.18, y-size*.20, sx+size*.18, y+size*.20,
                                   fill=col, outline="#101010", width=2)
                c.create_text(sx, y, text="+" if obj["kind"] == "medkit" else "$",
                              fill="#102010", font=("Consolas", max(8, int(size*.25)), "bold"))
            else:
                col = ENEMY_STATS[obj["mode"]]["color"]
                top = VIEW_H / 2 - size * .40
                bottom = VIEW_H / 2 + size * .48
                width = size * (.25 if obj["mode"] != "brute" else .36)
                c.create_oval(sx-width*.45, top, sx+width*.45, top+size*.28,
                              fill=col, outline="#191919", width=2)
                c.create_rectangle(sx-width*.55, top+size*.23, sx+width*.55, bottom,
                                   fill=col, outline="#191919", width=2)
                # Eyes and health pips make variants easier to distinguish.
                eye_y = top + size*.13
                c.create_oval(sx-width*.22, eye_y, sx-width*.08, eye_y+size*.04,
                              fill="#111111", outline="")
                c.create_oval(sx+width*.08, eye_y, sx+width*.22, eye_y+size*.04,
                              fill="#111111", outline="")
                if obj["hp"] > 1:
                    c.create_text(sx, top-size*.08, text=str(obj["hp"]),
                                  fill="white", font=("Consolas", max(8, int(size*.16)), "bold"))

        # Crosshair and weapon flash.
        cx, cy = VIEW_W // 2, VIEW_H // 2
        c.create_line(cx-9, cy, cx-3, cy, fill="white", width=2)
        c.create_line(cx+3, cy, cx+9, cy, fill="white", width=2)
        c.create_line(cx, cy-9, cx, cy-3, fill="white", width=2)
        c.create_line(cx, cy+3, cx, cy+9, fill="white", width=2)
        if self.flash_timer > 0:
            c.create_oval(cx-18, cy-18, cx+18, cy+18, outline="#ffd65a", width=3)

        # Right-side panel.
        panel_x = VIEW_W
        c.create_rectangle(panel_x, 0, WINDOW_W, WINDOW_H, fill="#171a20", outline="")
        c.create_text(panel_x+18, 22, anchor="w", text="WOLFENSTEIN 3D",
                      fill="#f2f2f2", font=("Consolas", 17, "bold"))
        c.create_text(panel_x+18, 48, anchor="w", text="HARD SURVIVAL",
                      fill="#e8b05b", font=("Consolas", 11, "bold"))
        self.draw_bar(panel_x+18, 78, 260, 16, self.player["hp"], START_HP, "#e65b4f", "HEALTH")
        self.draw_bar(panel_x+18, 116, 260, 16, self.player["ammo"], MAX_AMMO, "#e7c84f", "AMMO")
        alive = sum(e["alive"] for e in self.enemies)
        c.create_text(panel_x+18, 158, anchor="w",
                      text=f"KILLS {self.kills:02d}/{len(self.enemies)}   SCORE {self.score}",
                      fill="#ffffff", font=("Consolas", 11, "bold"))
        c.create_text(panel_x+18, 184, anchor="w",
                      text=f"SHOTS {self.shots}   ENEMIES LEFT {alive}",
                      fill="#b8c3d0", font=("Consolas", 10))
        # Minimap
        cell = 6.4
        ox, oy = panel_x + 18, 215
        c.create_text(ox, oy-12, anchor="w", text="MINIMAP",
                      fill="#d4dbe4", font=("Consolas", 10, "bold"))
        for y, row in enumerate(self.world):
            for x, tile in enumerate(row):
                if tile == "#":
                    c.create_rectangle(ox+x*cell, oy+y*cell, ox+(x+1)*cell, oy+(y+1)*cell,
                                       fill="#454b55", outline="")
        for item in self.pickups:
            if item["active"]:
                col = PICKUP_COLORS[item["kind"]]
                c.create_rectangle(ox+item["x"]*cell-2, oy+item["y"]*cell-2,
                                   ox+item["x"]*cell+2, oy+item["y"]*cell+2,
                                   fill=col, outline="")
        for e in self.enemies:
            if e["alive"]:
                c.create_oval(ox+e["x"]*cell-2, oy+e["y"]*cell-2,
                              ox+e["x"]*cell+2, oy+e["y"]*cell+2,
                              fill=ENEMY_STATS[e["mode"]]["color"], outline="")
        px, py = self.player["x"], self.player["y"]
        c.create_oval(ox+px*cell-3, oy+py*cell-3, ox+px*cell+3, oy+py*cell+3,
                      fill="#53e6ff", outline="white")
        c.create_line(ox+px*cell, oy+py*cell,
                      ox+(px+math.cos(self.player["angle"])*2)*cell,
                      oy+(py+math.sin(self.player["angle"])*2)*cell,
                      fill="#53e6ff", width=2)
        # Controls / message area
        c.create_text(panel_x+18, 430, anchor="w", text="CONTROLS",
                      fill="#d4dbe4", font=("Consolas", 10, "bold"))
        controls = ["W/S: move    A/D: strafe", "LEFT/RIGHT: turn", "SPACE: shoot",
                    "ESC: pause    N: new dungeon", "Q: quit", "+: medkit    $: ammo"]
        for i, line in enumerate(controls):
            c.create_text(panel_x+18, 452+i*19, anchor="w", text=line,
                          fill="#9da8b5", font=("Consolas", 9))
        c.create_rectangle(panel_x+12, 570, WINDOW_W-12, 642,
                           fill="#252a33", outline="#414957")
        c.create_text(panel_x+22, 581, anchor="nw", width=WINDOW_W-panel_x-44,
                      text=self.message, fill="#f2f2f2",
                      font=("Consolas", 10), justify="left")
        if self.paused or self.game_over or self.victory:
            label = "PAUSED" if self.paused else ("YOU DIED" if self.game_over else "DUNGEON CLEARED!")
            c.create_rectangle(160, 240, VIEW_W-160, 370,
                               fill="#111318", outline="#ffffff", width=2)
            c.create_text(VIEW_W/2, 280, text=label, fill="#ffffff",
                          font=("Consolas", 25, "bold"))
            c.create_text(VIEW_W/2, 325, text="Press N for a new dungeon" if not self.paused else "Press ESC to resume",
                          fill="#e8b05b", font=("Consolas", 12))

    def draw_bar(self, x, y, width, height, value, maximum, color, label):
        c = self.canvas
        c.create_text(x, y-8, anchor="sw", text=f"{label}: {value}/{maximum}",
                      fill="#d4dbe4", font=("Consolas", 10, "bold"))
        c.create_rectangle(x, y, x+width, y+height, fill="#333944", outline="")
        fill_width = width * max(0, value) / maximum
        c.create_rectangle(x, y, x+fill_width, y+height, fill=color, outline="")

    def tick(self):
        now = self.root.tk.call("clock", "milliseconds")
        if self.last_time is None:
            dt = 0.03
        else:
            dt = min(.06, max(.001, (int(now) - self.last_time) / 1000))
        self.last_time = int(now)
        self.frame += 1
        self.update(dt)
        self.draw()
        self.root.after(FPS_MS, self.tick)


def main():
    root = tk.Tk()
    Wolf3D(root)
    root.mainloop()


if __name__ == "__main__":
    main()
