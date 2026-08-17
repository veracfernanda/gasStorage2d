# gasStorage2d
gasStorage2d - templated OpenLB case executable

## About

`gasStorage2d` wraps an [OpenLB](https://www.openlb.net/) modified for a two-phase
Lattice Boltzmann simulation of gas displacing liquid (water) inside a porous rock, 
where part of the liquid stays trapped in the pore space and sets the effective 
porosity for gas-storage processes. Rather than editing the C++ solver by hand for
each run, an executable driver renders the solver from a template, injects parameters, 
builds it against OpenLB, and submits it to a SLURM cluster.

It is capable of:
- Rendering a compilable OpenLB solver (`gasStorage2d.cpp`) from the template `gasStorage2d.cpp.in` and the values in `params.yaml`
- Reading the porous geometry from an external `.vti` voxel file
- Building the case through the OpenLB example `make` target
- Submitting a single simulation or a multi-value parameter sweep to SLURM
- Staging a separate binary per case so concurrent jobs never overwrite each other
- Keeping a reproducible validation setup alongside the production case

## Installation

### Dependencies

Ensure you have the required dependencies installed, which are listed in `requirements.txt`. You can install them using:

```bash
pip install -r requirements.txt
```

Running the simulation itself additionally requires a working OpenLB build and
an MPI toolchain on the cluster. The `Makefile` used by the driver must point at
your OpenLB root and define the `gasStorage2d` target with MPI enabled
(`PARALLEL_MODE := MPI`), and the compiler/MPI modules named in the
`slurm.modules` block of `params.yaml` (default `GCC/13.2.0`, `OpenMPI/5.0.1`)
must be available.

### Folder structure

```bash
gasStorage2d
├─── README.md
├─── requirements.txt
├─── aptlcase
│   ├─── gasStorage2d.cpp.in
│   ├─── geometry-v0hor.vti
│   ├─── params.yaml
│   └─── run.py
└─── pathvalidation
    ├─── gasStorage2d.cpp
    └─── storage.vti
```
- **`aptlcase/`** — the executable production case. `run.py` reads `params.yaml`
  and the geometry `geometry-v0hor.vti`, renders `gasStorage2d.cpp.in` into a
  solver, builds it with OpenLB, and submits it. This is the folder you run.
- **`pathvalidation/`** — the reference setup used to validate the method: the
  already-rendered `gasStorage2d.cpp` and the geometry `storage.vti` it was
  checked against. It documents the known-good configuration the templated case
  is derived from.

## Usage
```bash
# sanity-check the parameter file parses into three blocks
python3 -c "import yaml;print(list(yaml.safe_load(open('params.yaml'))))"
#   -> ['vti', 'slurm', 'params']

# render + build + write submit.sh, but do NOT queue anything
./run.py --dry-run

# render, build and submit a single case
./run.py

# sweep one parameter across several values (one job each)
./run.py --sweep pressure_drop     --values 1000 2000 5000
./run.py --sweep contact_angle_deg --values 30 45 60
```

Each sweep value gets its own subdirectory (e.g. `pressure_drop_2000.0/`)
holding its staged binary, rendered source, `submit.sh`, and output.

To reproduce the validation case, compile and run `pathvalidation/gasStorage2d.cpp`
against `storage.vti` with OpenLB directly, following the standard OpenLB example
build.
