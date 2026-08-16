#!/usr/bin/env python3
import argparse, subprocess, shutil, re
from pathlib import Path
from copy import deepcopy
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent
CASE = "gasStorage2d"


def fmt(v):
    """Force C++-safe float literals."""
    return repr(v) if isinstance(v, float) else v


def slug(v):
    return re.sub(r"[^0-9A-Za-z._-]", "_", str(v))


def render(params, dest=None):
    env = Environment(
        loader=FileSystemLoader(ROOT),
        undefined=StrictUndefined,
        trim_blocks=True, lstrip_blocks=True,
    )
    src = env.get_template(f"{CASE}.cpp.in").render(**{k: fmt(v) for k, v in params.items()})
    out = Path(dest or ROOT / f"{CASE}.cpp")
    out.write_text(src)
    print(f"rendered -> {out}")
    return out


def build():
    subprocess.run(["make", "clean"], cwd=ROOT, check=False)
    subprocess.run(["make", CASE, "-j8"], cwd=ROOT, check=True)
    binary = ROOT / CASE
    if not binary.is_file():
        raise RuntimeError(f"build finished but {binary} is missing")
    return binary


def stage(binary, case_dir):
    """Copy binary + rendered source into the case dir so rebuilds can't race it."""
    case_dir.mkdir(parents=True, exist_ok=True)
    staged = case_dir / CASE
    shutil.copy2(binary, staged)
    shutil.copy2(ROOT / f"{CASE}.cpp", case_dir / f"{CASE}.cpp")
    return staged


def write_sbatch(case_dir, binary, sl, vti_file, vti_array):
    script = case_dir / "submit.sh"
    script.write_text(f"""#!/usr/bin/env bash
#SBATCH --job-name={sl['job_name']}
#SBATCH --partition={sl['partition']}
#SBATCH --nodes={sl['nodes']}
#SBATCH --ntasks={sl['ntasks']}
#SBATCH --ntasks-per-node={sl['ntasks_per_node']}
#SBATCH --cpus-per-task=1
#SBATCH --time={sl['time']}
#SBATCH --mem-per-cpu={sl['mem_per_cpu']}
#SBATCH --output={case_dir}/slurm-%j.out
#SBATCH --error={case_dir}/slurm-%j.err

set -euo pipefail

{chr(10).join(sl.get('modules', []))}

export OMP_NUM_THREADS=1

cd {case_dir}
srun {binary} "{vti_file}" "{vti_array}"
""")
    script.chmod(0o755)
    return script


def submit(script, depends_on=None):
    cmd = ["sbatch", "--parsable"]
    if depends_on:
        cmd.append(f"--dependency=afterok:{depends_on}")
    cmd.append(str(script))
    jid = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    print(f"submitted {script.name} -> job {jid}")
    return jid


def resolve_vti(vti):
    p = Path(vti["file"])
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"VTI not found: {p}")
    return p, vti["array"]


def one_case(params, sl, case_dir, vti, submit_job=True):
    vti_file, vti_array = resolve_vti(vti)
    render(params)
    binary = build()
    staged = stage(binary, case_dir)
    script = write_sbatch(case_dir, staged, sl, vti_file, vti_array)
    print(f"  case dir: {case_dir}")
    return submit(script) if submit_job else None


def main():
    ap = argparse.ArgumentParser(description="Render, build and submit OpenLB gasStorage2d cases.")
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--sweep", metavar="KEY", help="parameter key to vary")
    ap.add_argument("--values", nargs="+", help="values for --sweep")
    ap.add_argument("--dry-run", action="store_true",
                    help="render + build + write submit.sh, but do not sbatch")
    args = ap.parse_args()

    if args.sweep and not args.values:
        ap.error("--sweep requires --values")

    cfg = yaml.safe_load((ROOT / args.params).read_text())
    base, sl, vti = cfg["params"], cfg["slurm"], cfg["vti"]

    if args.sweep and args.sweep not in base:
        ap.error(f"unknown parameter '{args.sweep}'; not in {args.params}")

    if not args.sweep:
        one_case(base, sl, Path(base["output_dir"]), vti, submit_job=not args.dry_run)
        return

    root_out = Path(base["output_dir"])
    for raw in args.values:
        v = yaml.safe_load(raw)                    # "2000.0" -> float, "45" -> int
        p = deepcopy(base)
        p[args.sweep] = v
        case_dir = root_out / f"{args.sweep}_{slug(v)}"
        p["output_dir"] = str(case_dir) + "/"      # trailing slash: OpenLB concatenates
        s = deepcopy(sl)
        s["job_name"] = f"{sl['job_name']}_{args.sweep}_{slug(v)}"
        one_case(p, s, case_dir, vti, submit_job=not args.dry_run)


if __name__ == "__main__":
    main()