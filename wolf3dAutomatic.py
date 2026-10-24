import math
import random
import sys
import time
from collections import deque
from typing import Any

# ASCII WOLFENSTEIN: PROCEDURAL AUTO-PLAY DEMO
# Python standard library only. No input or keyboard API.
VIEW_W = 64
VIEW_H = 23
MAP_W = 39
MAP_H = 23
FOV = math.pi / 3
MAX_DEPTH = 24.0
FRAME_DELAY = 0.09
SIM_DT = 0.09
ENEMY_COUNT = 12
# The player is deliberately clumsy; enemies are faster and coordinate.
PLAYER_SPEED = 1.75
ENEMY_SPEED = 0.98
FIRE_COOLDOWN = 0.72
PLAYER_MISS_CHANCE = 0.32
PLAYER_AIM_SWAY = 0.20
ENEMY_NOTICE_RANGE = 13.0
ENEMY_MELEE_RANGE = 0.88
ENEMY_RANGED_RANGE = 7.5


# Explicit state declarations for type checkers and editor diagnostics.
Tile = tuple[int, int]
Room = tuple[int, int, int, int]

world: list[list[str]] = []
rooms: list[Room] = []
player: dict[str, Any] = {}
enemies: list[dict[str, Any]] = []
pickups: list[dict[str, Any]] = []
score: int = 0
shots: int = 0
message: str = ""
fire_timer: float = 0.0
nav_origin: Tile | None = None
nav_distance: dict[Tile, int] = {}
nav_parent: dict[Tile, Tile | None] = {}


def generate_dungeon() -> tuple[list[list[str]], list[Room]]:
    grid = [['#'] * MAP_W for _ in range(MAP_H)]
    room_list: list[Room] = []
    for _ in range(110):
        w, h = random.randint(4, 9), random.randint(3, 6)
        x = random.randint(1, MAP_W - w - 2)
        y = random.randint(1, MAP_H - h - 2)
        if any(x <= rx + rw and x + w >= rx and y <= ry + rh and y + h >= ry
               for rx, ry, rw, rh in room_list):
            continue
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                grid[yy][xx] = '.'
        if room_list:
            px, py, pw, ph = room_list[-1]
            ax, ay = px + pw // 2, py + ph // 2
            bx, by = x + w // 2, y + h // 2
            if random.choice([True, False]):
                for xx in range(min(ax, bx), max(ax, bx) + 1):
                    grid[ay][xx] = '.'
                for yy in range(min(ay, by), max(ay, by) + 1):
                    grid[yy][bx] = '.'
            else:
                for yy in range(min(ay, by), max(ay, by) + 1):
                    grid[yy][ax] = '.'
                for xx in range(min(ax, bx), max(ax, bx) + 1):
                    grid[by][xx] = '.'
        room_list.append((x, y, w, h))
        if len(room_list) >= 11:
            break
    if len(room_list) < 2:
        # A guaranteed fallback, although the random generator almost always succeeds.
        return generate_dungeon()
    return grid, room_list


def is_wall(x: float, y: float) -> bool:
    ix, iy = int(x), int(y)
    return not (0 <= ix < MAP_W and 0 <= iy < MAP_H) or world[iy][ix] == '#'


def angle_difference(a, b):
    return (a - b + math.pi) % (2 * math.pi) - math.pi


def move(entity, dx, dy):
    radius = 0.16
    nx, ny = entity['x'] + dx, entity['y'] + dy
    if not is_wall(nx + radius, entity['y']) and not is_wall(nx - radius, entity['y']):
        entity['x'] = nx
    if not is_wall(entity['x'], ny + radius) and not is_wall(entity['x'], ny - radius):
        entity['y'] = ny


def clear_shot(x1, y1, x2, y2):
    distance = math.hypot(x2 - x1, y2 - y1)
    steps = max(1, math.ceil(distance / 0.12))
    for i in range(1, steps):
        t = i / steps
        if is_wall(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t):
            return False
    return True


def path_to(start: Tile, goal: Tile) -> list[Tile]:
    if start == goal:
        return [start]
    queue = deque([start])
    parents: dict[Tile, Tile | None] = {start: None}
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (x + dx, y + dy)
            if nxt in parents or is_wall(nxt[0] + 0.5, nxt[1] + 0.5):
                continue
            parents[nxt] = (x, y)
            if nxt == goal:
                result: list[Tile] = [nxt]
                while True:
                    parent_tile = parents[result[-1]]
                    if parent_tile is None:
                        break
                    result.append(parent_tile)
                return result[::-1]
            queue.append(nxt)
    return []


def build_player_field(goal: Tile) -> tuple[dict[Tile, int], dict[Tile, Tile | None]]:
    """One BFS from the player's tile; each reachable tile points one step toward goal."""
    queue = deque([goal])
    parent: dict[Tile, Tile | None] = {goal: None}
    distance = {goal: 0}
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (x + dx, y + dy)
            if nxt in parent or is_wall(nxt[0] + 0.5, nxt[1] + 0.5):
                continue
            parent[nxt] = (x, y)
            distance[nxt] = distance[(x, y)] + 1
            queue.append(nxt)
    return distance, parent


def reset():
    global world, rooms, player, enemies, pickups, score, shots, message, fire_timer, nav_origin, nav_distance, nav_parent
    world, rooms = generate_dungeon()
    sx, sy, sw, sh = rooms[0]
    player = {'x': sx + sw // 2 + 0.5, 'y': sy + sh // 2 + 0.5,
              'angle': random.uniform(-math.pi, math.pi), 'hp': 90, 'ammo': 38}
    floor_tiles = [(x, y) for y in range(1, MAP_H - 1)
                   for x in range(1, MAP_W - 1)
                   if world[y][x] == '.' and
                   abs(x + 0.5 - player['x']) + abs(y + 0.5 - player['y']) > 8]
    random.shuffle(floor_tiles)
    enemy_modes = ['hunter', 'hunter', 'flanker', 'guard', 'brute', 'scout', 'sniper']
    enemies = []
    for x, y in floor_tiles[:ENEMY_COUNT]:
        mode = random.choice(enemy_modes)
        hp = {'hunter': 2, 'flanker': 2, 'guard': 3, 'brute': 5,
              'scout': 1, 'sniper': 2}[mode]
        enemies.append({'x': x + 0.5, 'y': y + 0.5, 'hp': hp, 'alive': True,
                        'attack_timer': random.uniform(0.2, 1.0), 'mode': mode,
                        'strafe': random.choice((-1, 1)), 'alert': False})
    # Pickups are placed on reachable floor tiles away from the player's start.
    occupied_enemy_tiles = {(int(e['x']), int(e['y'])) for e in enemies}
    pickup_tiles = [(x, y) for x, y in floor_tiles
                    if (x, y) not in occupied_enemy_tiles
                    and abs(x + 0.5 - player['x']) + abs(y + 0.5 - player['y']) > 3]
    random.shuffle(pickup_tiles)
    pickups = []
    for i, (x, y) in enumerate(pickup_tiles[:6]):
        pickups.append({'x': x + 0.5, 'y': y + 0.5,
                        'kind': 'medkit' if i < 3 else 'ammo', 'active': True})
    score = shots = 0
    message = 'HUNT EVERY ENEMY!'
    fire_timer = 0.0
    nav_origin = None
    nav_distance, nav_parent = {}, {}


def update(dt):
    global fire_timer, score, shots, message
    living = [e for e in enemies if e['alive']]
    if not living or player['hp'] <= 0:
        return

    fire_timer -= dt

    # Rebuild the navigation field only when the player enters a new map tile.
    # This replaces a separate full pathfinding search for every enemy each frame.
    global nav_origin, nav_distance, nav_parent
    current_tile = (int(player['x']), int(player['y']))
    if current_tile != nav_origin:
        nav_distance, nav_parent = build_player_field(current_tile)
        nav_origin = current_tile

    # Collect supplies when passing near them.
    for pickup in pickups:
        if not pickup['active']:
            continue
        dist_pickup = math.hypot(pickup['x'] - player['x'], pickup['y'] - player['y'])
        if dist_pickup < 0.55:
            if pickup['kind'] == 'medkit' and player['hp'] < 90:
                player['hp'] = min(90, player['hp'] + 25)
                pickup['active'] = False
                message = 'MEDKIT! +25 HP'
            elif pickup['kind'] == 'ammo' and player['ammo'] < 48:
                player['ammo'] = min(48, player['ammo'] + 12)
                pickup['active'] = False
                message = 'AMMO BOX! +12 ROUNDS'

    # Choose the closest enemy with a clear shot; keep moving even while firing.
    visible = [e for e in living
               if clear_shot(player['x'], player['y'], e['x'], e['y'])]
    target = min(visible, key=lambda e: math.hypot(e['x']-player['x'], e['y']-player['y'])) if visible else None

    # Navigation always runs. This fixes the old bug where seeing an enemy
    # caused the player to stop moving and shoot forever from one spot.
    if target is not None:
        dx, dy = target['x'] - player['x'], target['y'] - player['y']
        dist = max(0.001, math.hypot(dx, dy))
        desired = math.atan2(dy, dx)
        player['angle'] += max(-2.4*dt, min(2.4*dt, angle_difference(desired, player['angle'])))
        player['angle'] += random.uniform(-PLAYER_AIM_SWAY, PLAYER_AIM_SWAY) * dt

        # Close the distance when far away; strafe/advance gently at combat range.
        if dist > 3.0:
            route = path_to((int(player['x']), int(player['y'])),
                            (int(target['x']), int(target['y'])))
            if route and len(route) > 1:
                gx, gy = route[1][0] + 0.5, route[1][1] + 0.5
                vx, vy = gx-player['x'], gy-player['y']
                length = max(0.001, math.hypot(vx, vy))
                move(player, vx/length*PLAYER_SPEED*dt, vy/length*PLAYER_SPEED*dt)
        elif dist > 1.7:
            # Small side-step prevents stationary turret behavior.
            side = random.choice((-1, 1))
            move(player, (-dy/dist)*side*PLAYER_SPEED*0.48*dt,
                 (dx/dist)*side*PLAYER_SPEED*0.48*dt)
        elif dist < 1.2:
            # Back away when an enemy gets dangerously close.
            move(player, -dx/dist*PLAYER_SPEED*0.75*dt,
                 -dy/dist*PLAYER_SPEED*0.75*dt)

        if fire_timer <= 0:
            if player['ammo'] <= 0:
                message = 'OUT OF AMMO! FIND AMMO BOXES!'
                fire_timer = 0.35
            elif abs(angle_difference(desired, player['angle'])) < 0.50:
                shots += 1
                player['ammo'] -= 1
                fire_timer = FIRE_COOLDOWN
                if random.random() < PLAYER_MISS_CHANCE or dist > 7.0:
                    message = 'MISSED SHOT'
                else:
                    target['hp'] -= 1
                    message = 'HIT!'
                    if target['hp'] <= 0:
                        target['alive'] = False
                        score += 100
                        message = f'{target["mode"].upper()} DEFEATED! +100'
    else:
        # No line of sight: follow a route toward the nearest living enemy.
        if living:
            reachable = [(nav_distance.get((int(e['x']), int(e['y'])), 10**6), e)
                         for e in living]
            distance_to_enemy, nearest = min(reachable, key=lambda item: item[0])
            if distance_to_enemy < 10**6:
                goal = (int(nearest['x']), int(nearest['y']))
                route = path_to(current_tile, goal)
                if len(route) > 1:
                    gx, gy = route[1][0] + 0.5, route[1][1] + 0.5
                    dx, dy = gx-player['x'], gy-player['y']
                    dist = max(0.001, math.hypot(dx, dy))
                    player['angle'] += max(-2.4*dt, min(2.4*dt,
                                                angle_difference(math.atan2(dy, dx), player['angle'])))
                    move(player, dx/dist*PLAYER_SPEED*dt, dy/dist*PLAYER_SPEED*dt)
            message = 'SEARCHING FOR ENEMIES...'

    # Enemies have distinct roles, but their pace is moderate.
    for enemy in enemies:
        if not enemy['alive']:
            continue
        dx, dy = player['x']-enemy['x'], player['y']-enemy['y']
        dist = max(0.001, math.hypot(dx, dy))
        los = clear_shot(enemy['x'], enemy['y'], player['x'], player['y'])
        if dist < ENEMY_NOTICE_RANGE:
            enemy['alert'] = True
        if not enemy['alert']:
            continue

        enemy['attack_timer'] += dt
        if dist < ENEMY_MELEE_RANGE:
            cooldown = 1.35 if enemy['mode'] == 'brute' else 1.7
            if enemy['attack_timer'] >= cooldown:
                enemy['attack_timer'] = 0.0
                damage = random.randint(6, 9) if enemy['mode'] == 'brute' else random.randint(3, 6)
                player['hp'] = max(0, player['hp'] - damage)
                message = f'{enemy["mode"].upper()} HITS! -{damage} HP'
            continue

        if enemy['mode'] in ('guard', 'sniper') and los and dist < (11 if enemy['mode'] == 'sniper' else 7) and dist > 2.5:
            cooldown = 1.9 if enemy['mode'] == 'sniper' else 2.3
            if enemy['attack_timer'] >= cooldown:
                enemy['attack_timer'] = 0.0
                damage = random.randint(5, 8) if enemy['mode'] == 'sniper' else random.randint(3, 6)
                player['hp'] = max(0, player['hp'] - damage)
                message = f'{enemy["mode"].upper()} SHOT! -{damage} HP'
            if dist < 3.5:
                move(enemy, -dx/dist*ENEMY_SPEED*dt, -dy/dist*ENEMY_SPEED*dt)
            continue

        speed = ENEMY_SPEED
        if enemy['mode'] == 'brute':
            speed *= 0.72
        elif enemy['mode'] == 'scout':
            speed *= 1.35
        elif enemy['mode'] == 'flanker':
            speed *= 0.92
        enemy_tile = (int(enemy['x']), int(enemy['y']))
        next_tile = nav_parent.get(enemy_tile)
        if next_tile is not None:
            gx, gy = next_tile[0] + 0.5, next_tile[1] + 0.5
            vx, vy = gx-enemy['x'], gy-enemy['y']
        else:
            # If a tile is disconnected from the current field, move directly
            # only when there is line of sight; otherwise stay instead of jittering.
            vx, vy = (dx, dy) if los else (0.0, 0.0)
        length = max(0.001, math.hypot(vx, vy))
        move(enemy, vx/length*speed*dt, vy/length*speed*dt)


def render(_frame: int):
    screen = [[' ' if y < VIEW_H // 2 else (':' if y > VIEW_H * 3 // 4 else '.')
               for _ in range(VIEW_W)] for y in range(VIEW_H)]
    depths = [MAX_DEPTH] * VIEW_W
    for col in range(VIEW_W):
        a = player['angle'] + (col / VIEW_W - 0.5) * FOV
        rx, ry = math.cos(a), math.sin(a)
        distance = 0.03
        while distance < MAX_DEPTH and not is_wall(player['x'] + rx * distance,
                                                   player['y'] + ry * distance):
            distance += 0.055
        corrected = max(0.1, distance * math.cos(a - player['angle']))
        depths[col] = corrected
        size = int(VIEW_H / corrected)
        top = max(0, VIEW_H // 2 - size // 2)
        bottom = min(VIEW_H - 1, VIEW_H // 2 + size // 2)
        shade = '#' if corrected < 2 else 'X' if corrected < 4 else '=' if corrected < 7 else '-' if corrected < 11 else '.'
        for y in range(top, bottom + 1):
            screen[y][col] = shade

    sprites = []
    for enemy in enemies:
        if not enemy['alive']:
            continue
        dx, dy = enemy['x'] - player['x'], enemy['y'] - player['y']
        dist = math.hypot(dx, dy)
        relative = angle_difference(math.atan2(dy, dx), player['angle'])
        if dist > 0.1 and abs(relative) < FOV / 2 + 0.15:
            sprites.append((dist, relative, enemy))
    for dist, relative, enemy in sorted(sprites, key=lambda x: -x[0]):
        corrected = max(0.1, dist * math.cos(relative))
        sx = int((0.5 + relative / FOV) * VIEW_W)
        size = max(1, int(VIEW_H / corrected))
        half_width = max(0, size // 4)
        top = max(1, VIEW_H // 2 - size // 2)
        bottom = min(VIEW_H - 2, VIEW_H // 2 + size // 2)
        for x in range(max(0, sx - half_width), min(VIEW_W, sx + half_width + 1)):
            if corrected < depths[x]:
                for y in range(top, bottom + 1):
                    screen[y][x] = {'guard':'W', 'sniper':'S', 'brute':'B', 'scout':'s', 'flanker':'F', 'hunter':'E'}.get(enemy['mode'], 'E')

    # Render supply boxes as simple ASCII sprites.
    for pickup in pickups:
        if not pickup['active']:
            continue
        dx, dy = pickup['x'] - player['x'], pickup['y'] - player['y']
        dist = math.hypot(dx, dy)
        relative = angle_difference(math.atan2(dy, dx), player['angle'])
        if dist > 0.2 and abs(relative) < FOV / 2:
            sx = int((0.5 + relative / FOV) * VIEW_W)
            if 0 <= sx < VIEW_W and dist * math.cos(relative) < depths[sx]:
                screen[VIEW_H // 2][sx] = '+' if pickup['kind'] == 'medkit' else '$'

    screen[VIEW_H // 2][VIEW_W // 2] = '+'
    alive = sum(e['alive'] for e in enemies)
    hud = f'HP:{player["hp"]:3} AMMO:{player["ammo"]:2} KILLS:{len(enemies)-alive}/{len(enemies)} SCORE:{score}'
    for i, ch in enumerate(hud[:VIEW_W]):
        screen[0][i] = ch
    for i, ch in enumerate(message[:VIEW_W]):
        screen[VIEW_H - 2][i] = ch
    return [''.join(row) for row in screen]


def minimap():
    view = [row[:] for row in world]
    for enemy in enemies:
        if enemy['alive']:
            view[int(enemy['y'])][int(enemy['x'])] = {'hunter':'E', 'flanker':'F', 'guard':'W', 'brute':'B', 'scout':'s', 'sniper':'S'}.get(enemy['mode'], 'E')
    for pickup in pickups:
        if pickup['active']:
            view[int(pickup['y'])][int(pickup['x'])] = '+' if pickup['kind'] == 'medkit' else '$'
    px, py = int(player['x']), int(player['y'])
    view[py][px] = 'P'
    return [''.join(row) for row in view]


def display(frame):
    view = render(frame)
    mini = minimap()
    lines = ['ASCII WOLFENSTEIN 3D - PROCEDURAL DUNGEON',
             '3D VIEW'.ljust(VIEW_W + 3) + 'MAP: P=YOU E=HUNTER F=FLANKER W=GUARD B=BRUTE s=SCOUT S=SNIPER +=MEDKIT $=AMMO']
    for i in range(max(VIEW_H, MAP_H)):
        left = view[i] if i < VIEW_H else ' ' * VIEW_W
        right = mini[i] if i < MAP_H else ''
        lines.append(left + '   ' + right)
    lines.append('HARD SURVIVAL: 12 enemies | 90 HP | limited ammo | cached pathfinding.')
    sys.stdout.write('\033[H\033[2J' + '\n'.join(lines) + '\n')
    sys.stdout.flush()


def main():
    reset()
    frame = 0
    try:
        while player['hp'] > 0 and any(e['alive'] for e in enemies):
            update(SIM_DT)
            display(frame)
            frame += 1
            time.sleep(FRAME_DELAY)
        display(frame)
        if player['hp'] > 0:
            print('\nMISSION COMPLETE! ALL ENEMIES DEFEATED!')
        else:
            print('\nGAME OVER: THE PLAYER WAS DEFEATED.')
        print('Kills:', sum(not e['alive'] for e in enemies), '/', len(enemies))
        print('Score:', score, '| Shots:', shots, '| Ammo left:', player['ammo'])
    except KeyboardInterrupt:
        print('\nDemo interrupted.')


if __name__ == '__main__':
    main()
