from voxflow.particles import ParticleField


def test_particles_flow_and_react_to_nearby_cursor():
    calm = ParticleField(820, 300, seed=7)
    disturbed = ParticleField(820, 300, seed=7)
    assert len(calm.particles) >= 600
    target = disturbed.particles[len(disturbed.particles) // 2]
    pointer = (target.x - 10, target.y)
    before = (target.x, target.y)

    for _ in range(8):
        calm.step(None)
        disturbed.step(pointer)

    moved = disturbed.particles[len(disturbed.particles) // 2]
    counterpart = calm.particles[len(calm.particles) // 2]
    assert (moved.x, moved.y) != before
    assert moved.x > counterpart.x + 2


def test_particle_field_resizes_with_overlay():
    field = ParticleField(820, 300, seed=7)
    original = field.particles[0].x
    field.resize(410, 150)
    assert field.width == 410
    assert field.particles[0].x == original / 2


def test_particle_clock_uses_elapsed_time():
    field = ParticleField(820, 300)
    field.step(None, dt=1 / 60)
    assert abs(field.time - 1 / 60) < 1e-9


def test_particle_seeds_cover_the_surface_without_an_oval_outline():
    field = ParticleField(820, 300)
    top = [p for p in field.particles if p.y < 75]
    middle = [p for p in field.particles if 120 < p.y < 180]
    assert len(top) > 100
    assert max(p.x for p in top) - min(p.x for p in top) > 0.85 * field.width
    assert max(p.x for p in middle) - min(p.x for p in middle) > 0.85 * field.width
    average_opacity = sum(p.opacity for p in field.particles) / len(field.particles)
    assert 95 <= average_opacity <= 140


def test_particle_motion_responds_to_audio_energy():
    quiet = ParticleField(820, 300, seed=7)
    speaking = ParticleField(820, 300, seed=7)
    for _ in range(20):
        quiet.step(None, dt=1 / 60, energy=0)
        speaking.step(None, dt=1 / 60, energy=0.8)
    movement = ((quiet.particles[400].x - speaking.particles[400].x) ** 2
                + (quiet.particles[400].y - speaking.particles[400].y) ** 2) ** 0.5
    assert 1 < movement < 8
