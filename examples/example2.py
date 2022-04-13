# import oommfc as mc
import discretisedfield as df

import mumaxc as mc

L = 10e-9
d = 1e-9
Ms = 8e6  # saturation magnetisation (A/m)
A = 1e-12  # exchange energy constant (J/m)
H = (5e6, 0, 0)  # external magnetic field in the x-direction (A/m)
gamma = 2.211e5  # gamma parameter (m/As)
alpha = 0.2  # Gilbert damping

mesh = mc.Mesh(p1=(0, 0, 0), p2=(L, L, L), cell=(d, d, d))
system = mc.System(name="example2")
system.hamiltonian = mc.Exchange(A=A) + mc.Demag() + mc.Zeeman(H=H)
system.dynamics = mc.Precession(gamma=gamma) + mc.Damping(alpha=alpha)
system.m = df.Field(mesh, value=(0, 0, 1), norm=Ms)

td = mc.TimeDriver()
td.drive(system, t=1e-9, n=10, overwrite=True)

mx, my, mz = system.m.average

assert mx > my
assert mx > mz

print(system.m.average)
