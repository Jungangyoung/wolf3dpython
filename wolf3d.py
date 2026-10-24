
import math
import os
import random
import subprocess
import sys
import time

# Real-time keyboard input requires a Windows console.
if os.name != "nt":
    print("This version requires Windows.")
    raise SystemExit

if "--console" not in sys.argv:
    script = globals().get("__file__")
    if not script:
        print("Save this as wolf3d_ascii.py and press F5.")
        raise SystemExit
    subprocess.Popen(
        ["cmd", "/c", "start", "Wolf3D ASCII",
         sys.executable, os.path.abspath(script), "--console"],
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )
    print("Play in the new terminal window.")
    raise SystemExit

import msvcrt

try:
    import ctypes
    k32 = ctypes.windll.kernel32
    handle = k32.GetStdHandle(-11)
    mode = ctypes.c_uint()
    if k32.GetConsoleMode(handle, ctypes.byref(mode)):
        k32.SetConsoleMode(handle, mode.value | 4)
except Exception:
    pass

W, H = 31, 21
RAYS, VH = 70, 13
FOV = math.radians(68)
MAX_HP, MAX_AMMO = 100, 54

# Symbol, name, HP, speed, damage, AI behavior
ENEMIES = [
    ("E", "Hunter",       28, 1.15, 1, "chase"),
    ("F", "Flanker",      20, 1.55, 1, "flank"),
    ("G", "Guard",        42, 0.75, 2, "chase"),
    ("B", "Brute",        68, 0.58, 3, "tank"),
    ("s", "Scout",        17, 1.85, 1, "fast"),
    ("S", "Sniper",       24, 0.68, 2, "sniper"),
    ("M", "Mutant",       36, 1.05, 2, "chase"),
    ("T", "Stalker",      30, 1.30, 2, "flank"),
    ("D", "Demolisher",   54, 0.82, 3, "tank"),
    ("C", "Commander",    48, 1.00, 2, "leader"),
    ("Z", "Zombie",       45, 0.50, 2, "tank"),
    ("V", "Viper",        16, 2.00, 1, "fast"),
    ("R", "Reaper",       38, 1.45, 3, "flank"),
    ("W", "Warlock",      32, 0.90, 2, "sniper"),
    ("K", "Knight",       78, 0.65, 4, "tank"),
    ("A", "Assassin",     22, 1.75, 2, "flank"),
    ("O", "Overlord",    100, 0.72, 4, "leader"),
    ("X", "Experiment",   60, 1.20, 3, "chase"),
    ("I", "Imp",          14, 1.90, 1, "fast"),
    ("Y", "Juggernaut",   90, 0.48, 5, "tank"),
]

DIFFICULTY = {
    "1": dict(name="EASY", count=8, hp=.75, speed=.82,
              damage=.65, tick=.55, ammo=42),
    "2": dict(name="NORMAL", count=12, hp=1.0, speed=1.0,
              damage=1.0, tick=.42, ammo=36),
    "3": dict(name="HARD", count=18, hp=1.30, speed=1.20,
              damage=1.50, tick=.31, ammo=30),
}


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def open_tile(grid, x, y):
    ix, iy = int(x), int(y)
    return 0 <= ix < W and 0 <= iy < H and grid[iy][ix] != "#"


def generate_map():
    grid = [["#" for _ in range(W)] for _ in range(H)]
    grid[1][1] = " "
    stack = [(1, 1)]

    while stack:
        x, y = stack[-1]
        choices = []
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            nx, ny = x + dx, y + dy
            if 1 <= nx < W-1 and 1 <= ny < H-1:
                if grid[ny][nx] == "#":
                    choices.append((nx, ny, dx, dy))
        if choices:
            nx, ny, dx, dy = random.choice(choices)
            grid[y + dy//2][x + dx//2] = " "
            grid[ny][nx] = " "
            stack.append((nx, ny))
        else:
            stack.pop()

    # Extra openings create loops.
    for _ in range(55):
        x, y = random.randrange(1, W-1), random.randrange(1, H-1)
        if grid[y][x] != "#":
            continue
        adjacent = sum(
            grid[y+dy][x+dx] == " "
            for dx, dy in ((1,0),(-1,0),(0,1),(0,-1))
        )
        if adjacent >= 2:
            grid[y][x] = " "
    return grid


class Game:
    def __init__(self, level="2"):
        self.level = level
        self.rules = DIFFICULTY[level]
        self.grid = generate_map()
        self.px, self.py = 1.5, 1.5
        self.angle = 0.0
        self.hp = MAX_HP
        self.ammo = self.rules["ammo"]
        self.kills = 0
        self.score = 0
        self.running = True
        self.message = "Explore! Find enemies, medkits (+), and ammo ($)."
        self.enemies = []
        self.items = {}
        self.last_ai = time.monotonic()
        self.spawn()

    def spawn(self):
        spots = [
            (x+.5, y+.5)
            for y in range(1, H-1)
            for x in range(1, W-1)
            if self.grid[y][x] == " "
            and dist((x+.5, y+.5), (self.px, self.py)) > 5
        ]
        random.shuffle(spots)

        for _ in range(min(self.rules["count"], len(spots))):
            x, y = spots.pop()
            symbol, name, hp, speed, damage, behavior = random.choice(ENEMIES)
            hp = max(1, int(hp * self.rules["hp"]))
            self.enemies.append(dict(
                x=x, y=y, symbol=symbol, name=name, hp=hp,
                speed=speed*self.rules["speed"],
                damage=max(1, int(damage*self.rules["damage"])),
                behavior=behavior
            ))

        for _ in range(12):
            if spots:
                x, y = spots.pop()
                self.items[int(x), int(y)] = random.choice(["+", "$", "$"])

        self.message = (
            f"{self.rules['name']}: {len(self.enemies)} enemies. "
            "Use the local radar to find them."
        )

    def line_of_sight(self, x1, y1, x2, y2):
        steps = max(2, int(dist((x1,y1),(x2,y2))*12))
        for i in range(1, steps):
            t = i / steps
            if not open_tile(
                self.grid, x1+(x2-x1)*t, y1+(y2-y1)*t
            ):
                return False
        return True

    def move(self, dx, dy):
        nx, ny = self.px+dx, self.py+dy
        if open_tile(self.grid, nx, self.py) and all(
            dist((nx,self.py),(e["x"],e["y"])) > .45
            for e in self.enemies
        ):
            self.px = nx
        if open_tile(self.grid, self.px, ny) and all(
            dist((self.px,ny),(e["x"],e["y"])) > .45
            for e in self.enemies
        ):
            self.py = ny

        item = self.items.pop((int(self.px),int(self.py)), None)
        if item == "+":
            old = self.hp
            self.hp = min(MAX_HP, self.hp+30)
            self.message = f"Medkit: +{self.hp-old} HP."
        elif item == "$":
            old = self.ammo
            self.ammo = min(MAX_AMMO, self.ammo+12)
            self.message = f"Ammo box: +{self.ammo-old} rounds."

    def shoot(self):
        if self.ammo <= 0:
            self.message = "Out of ammo! Find a $ box."
            return
        self.ammo -= 1
        target, target_dist = None, 999

        for e in self.enemies:
            d = dist((self.px,self.py),(e["x"],e["y"]))
            if d > 11 or d >= target_dist:
                continue
            bearing = math.atan2(e["y"]-self.py,e["x"]-self.px)
            delta = (bearing-self.angle+math.pi)%(2*math.pi)-math.pi
            if abs(delta) < math.radians(9) and self.line_of_sight(
                self.px,self.py,e["x"],e["y"]
            ):
                target, target_dist = e, d

        if target is None:
            self.message = "Miss! Aim toward an enemy and shoot."
            return

        damage = random.randint(20, 32)
        target["hp"] -= damage
        if target["hp"] <= 0:
            self.enemies.remove(target)
            self.kills += 1
            self.score += 100
            self.message = f"{target['name']} defeated! +100 points."
        else:
            self.message = (
                f"Hit {target['name']} for {damage}. "
                f"Remaining HP: {target['hp']}."
            )

    def update_ai(self):
        now = time.monotonic()
        if now-self.last_ai < self.rules["tick"]:
            return
        self.last_ai = now

        for e in self.enemies:
            d = dist((self.px,self.py),(e["x"],e["y"]))
            if d < 1.15:
                damage = e["damage"]*random.randint(2,4)
                self.hp -= damage
                self.message = f"{e['name']} attacks for {damage} damage!"
                continue

            if d > 13 or not self.line_of_sight(
                e["x"],e["y"],self.px,self.py
            ):
                continue

            if e["behavior"] == "sniper" and d < 10 and random.random() < .35:
                damage = max(2,int(5*self.rules["damage"]))
                self.hp -= damage
                self.message = f"{e['name']} shoots you for {damage} HP!"
                continue

            vx = (self.px-e["x"])/max(d,.001)
            vy = (self.py-e["y"])/max(d,.001)

            if e["behavior"] == "flank" and d > 1.5:
                side = .45 if int(now*2+e["x"])%2 else -.45
                vx, vy = vx-vy*side, vy+vx*side

            step = e["speed"]*self.rules["tick"]
            nx, ny = e["x"]+vx*step, e["y"]+vy*step
            if open_tile(self.grid,nx,e["y"]):
                e["x"] = nx
            if open_tile(self.grid,e["x"],ny):
                e["y"] = ny

        if self.hp <= 0:
            self.hp = 0
            self.running = False
            self.message = "YOU DIED! Press R to restart or Q to quit."

    def render(self):
        # Raycast walls.
        rows = [[" "]*RAYS for _ in range(VH)]
        zbuf = [30.0]*RAYS

        for col in range(RAYS):
            angle = self.angle-FOV/2+(col/RAYS)*FOV
            d = .04
            while d < 20:
                x = self.px+math.cos(angle)*d
                y = self.py+math.sin(angle)*d
                if not open_tile(self.grid,x,y):
                    break
                d += .045

            d = max(.1,d*math.cos(angle-self.angle))
            zbuf[col] = d
            height = min(12,int(11/d))
            top = max(0,6-height//2)
            bottom = min(VH-1,top+height)
            shade = "#" if d<3 else "+" if d<5 else ":" if d<8 else "."
            for yy in range(top,bottom):
                rows[yy][col] = shade
            for yy in range(bottom,VH):
                rows[yy][col] = "," if yy>10 else "."

        # Render enemy silhouettes, nearest in front.
        for e in sorted(
            self.enemies,
            key=lambda e: dist((self.px,self.py),(e["x"],e["y"])),
            reverse=True
        ):
            d = dist((self.px,self.py),(e["x"],e["y"]))
            if d > 16:
                continue
            bearing = math.atan2(e["y"]-self.py,e["x"]-self.px)
            delta = (bearing-self.angle+math.pi)%(2*math.pi)-math.pi
            if abs(delta) >= FOV/2:
                continue
            if not self.line_of_sight(self.px,self.py,e["x"],e["y"]):
                continue

            col = int((delta/FOV+.5)*RAYS)
            if not 0 <= col < RAYS:
                continue
            symbol = e["symbol"]
            sprite = [" .-. ", f"({symbol}{symbol}{symbol})", f" /{symbol}\\ ", " /|\\ ", " / \\ "]
            top = max(0,6-min(4,int(9/max(d,.5)))
                      )
            for r, text in enumerate(sprite):
                yy = top+r
                if yy >= VH:
                    continue
                left = col-len(text)//2
                for i,ch in enumerate(text):
                    xx = left+i
                    if 0 <= xx < RAYS and ch != " " and d < zbuf[xx]+.3:
                        rows[yy][xx] = ch

        hpbar = "#"*(self.hp//5)+"-"*(20-self.hp//5)
        lines = [
            f"WOLF3D ASCII | {self.rules['name']}",
            f"HP [{hpbar}] {self.hp:3d}  AMMO {self.ammo:02d}  "
            f"KILLS {self.kills:02d}  SCORE {self.score:04d}  "
            f"ENEMIES {len(self.enemies):02d}",
            "+"+"-"*RAYS+"+",
        ]
        lines += ["|"+''.join(row)+"|" for row in rows]
        lines += ["+"+"-"*RAYS+"+", "LOCAL RADAR: P=you, enemy symbols, +=medkit, $=ammo"]

        # Compact 13 x 9 minimap around the player.
        cx, cy = int(self.px), int(self.py)
        for y in range(cy-4,cy+5):
            line = []
            for x in range(cx-6,cx+7):
                if not (0 <= x < W and 0 <= y < H):
                    line.append("#")
                elif x == cx and y == cy:
                    line.append("P")
                elif any(
                    int(e["x"]) == x and int(e["y"]) == y
                    for e in self.enemies
                ):
                    e = next(
                        e for e in self.enemies
                        if int(e["x"]) == x and int(e["y"]) == y
                    )
                    line.append(e["symbol"])
                elif (x,y) in self.items:
                    line.append(self.items[x,y])
                else:
                    line.append(self.grid[y][x])
            lines.append(''.join(line))

        lines += [
            self.message,
            "W/S move | A/D turn | J/L strafe | SPACE shoot",
            "1 Easy | 2 Normal | 3 Hard | R restart | Q quit",
        ]
        return "\n".join(lines)


def main():
    game = Game("2")
    last_frame = 0
    print("\x1b[2J\x1b[H\x1b[?25l",end="",flush=True)

    try:
        while True:
            if game.running:
                game.update_ai()

            key = None
            while msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\x00","\xe0"):
                    if msvcrt.kbhit():
                        msvcrt.getwch()
                    continue
                key = ch.lower()

            if key == "q":
                break
            if key in ("1","2","3"):
                game = Game(key)
            elif not game.running:
                if key == "r":
                    game = Game(game.level)
            elif key:
                step = .19
                turn = math.radians(5)
                if key == "w":
                    game.move(math.cos(game.angle)*step,math.sin(game.angle)*step)
                elif key == "s":
                    game.move(-math.cos(game.angle)*step,-math.sin(game.angle)*step)
                elif key == "a":
                    game.angle -= turn
                elif key == "d":
                    game.angle += turn
                elif key == "j":
                    game.move(math.cos(game.angle-math.pi/2)*step,
                              math.sin(game.angle-math.pi/2)*step)
                elif key == "l":
                    game.move(math.cos(game.angle+math.pi/2)*step,
                              math.sin(game.angle+math.pi/2)*step)
                elif key == " ":
                    game.shoot()

            now = time.monotonic()
            if now-last_frame > 1/18 or key:
                print("\x1b[H\x1b[J"+game.render(),end="",flush=True)
                last_frame = now
            time.sleep(.008)
    finally:
        print("\x1b[?25h\x1b[0m\n",end="",flush=True)

    print("Thanks for playing!")


if __name__ == "__main__":
    main()
