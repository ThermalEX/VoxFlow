"""Small deterministic particle field with gentle flow and cursor repulsion."""

import math
import random
from dataclasses import dataclass


@dataclass(slots=True)
class Particle:
    anchor_x: float
    anchor_y: float
    x: float
    y: float
    phase: float
    radius: float
    opacity: int
    vx: float = 0.0
    vy: float = 0.0


class ParticleField:
    def __init__(self, width: int, height: int, seed: int = 31) -> None:
        self.width = width
        self.height = height
        self.time = 0.0
        self.pointer: tuple[float, float] | None = None
        rng = random.Random(seed)
        self.particles: list[Particle] = []
        columns, rows = 32, 20
        for row in range(rows):
            for column in range(columns):
                x = width * (column + 0.5 + rng.uniform(-0.35, 0.35)) / columns
                y = height * (row + 0.5 + rng.uniform(-0.35, 0.35)) / rows
                self.particles.append(
                    Particle(x, y, x, y, rng.uniform(0, 2 * math.pi),
                             rng.uniform(0.6, 1.0), rng.randint(45, 95))
                )

    def resize(self, width: int, height: int) -> None:
        if width == self.width and height == self.height:
            return
        scale_x = width / self.width
        scale_y = height / self.height
        for particle in self.particles:
            particle.anchor_x *= scale_x
            particle.anchor_y *= scale_y
            particle.x *= scale_x
            particle.y *= scale_y
            particle.vx *= scale_x
            particle.vy *= scale_y
        self.width = width
        self.height = height

    def step(self, pointer: tuple[float, float] | None, dt: float = 1 / 30, energy: float = 0.0) -> None:
        self.time += dt
        self.pointer = pointer
        energy = max(0.0, min(1.0, energy))
        frame_scale = dt * 30
        damping = 0.90 ** frame_scale
        for particle in self.particles:
            drift_x = math.sin(self.time * (0.72 + energy * 2.0) + particle.phase) * (3.5 + energy * 13)
            drift_y = math.cos(self.time * (0.58 + energy * 1.7) + particle.phase) * (3.0 + energy * 11)
            target_x = particle.anchor_x + drift_x
            target_y = particle.anchor_y + drift_y
            particle.vx += (target_x - particle.x) * 0.025 * frame_scale
            particle.vy += (target_y - particle.y) * 0.025 * frame_scale
            if pointer is not None:
                dx, dy = particle.x - pointer[0], particle.y - pointer[1]
                distance = math.hypot(dx, dy)
                if 0 < distance < 142:
                    force = (1 - distance / 142) ** 2 * 3.0 * frame_scale
                    particle.vx += dx / distance * force
                    particle.vy += dy / distance * force
            particle.vx *= damping
            particle.vy *= damping
            particle.x += particle.vx * frame_scale
            particle.y += particle.vy * frame_scale
