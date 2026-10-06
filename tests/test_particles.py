from voxflow.particles import ParticleField


def test_particles_flow_and_react_to_nearby_cursor():
    calm = ParticleField(820, 300, seed=7)
    disturbed = ParticleField(820, 300, seed=7)
    assert len(calm.particles) >= 700
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


def test_particles_form_a_soft_cloud_instead_of_a_rectangle():
    field = ParticleField(820, 300)
    top = [p for p in field.particles if p.y < 75]
    middle = [p for p in field.particles if 120 < p.y < 180]
    assert len(middle) > len(top)
    assert max(p.x for p in top) - min(p.x for p in top) < max(p.x for p in middle) - min(p.x for p in middle)


def test_particle_motion_responds_to_audio_energy():
    quiet = ParticleField(820, 300, seed=7)
    speaking = ParticleField(820, 300, seed=7)
    for _ in range(20):
        quiet.step(None, dt=1 / 60, energy=0)
        speaking.step(None, dt=1 / 60, energy=0.8)
    assert abs(quiet.particles[400].x - speaking.particles[400].x) > 1
