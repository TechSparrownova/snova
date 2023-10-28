# imports - standard imports
import grp
import os
import pwd
import shutil
import sys

# imports - module imports
import snova
from snova.utils import (
	exec_cmd,
	get_process_manager,
	log,
	run_saps_cmd,
	sudoers_file,
	which,
	is_valid_saps_branch,
)
from snova.utils.snova import build_assets, clone_apps_from
from snova.utils.render import job


@job(title="Initializing Snova {path}", success="Snova {path} initialized")
def init(
	path,
	apps_path=None,
	no_procfile=False,
	no_backups=False,
	saps_path=None,
	saps_branch=None,
	verbose=False,
	clone_from=None,
	skip_redis_config_generation=False,
	clone_without_update=False,
	skip_assets=False,
	python="python3",
	install_app=None,
):
	"""Initialize a new snova directory

	* create a snova directory in the given path
	* setup logging for the snova
	* setup env for the snova
	* setup config (dir/pids/redis/procfile) for the snova
	* setup patches.txt for snova
	* clone & install sparrow
	        * install python & node dependencies
	        * build assets
	* setup backups crontab
	"""

	# Use print("\033c", end="") to clear entire screen after each step and re-render each list
	# another way => https://stackoverflow.com/a/44591228/10309266

	import snova.cli
	from snova.app import get_app, install_apps_from_path
	from snova.snova import Snova

	verbose = snova.cli.verbose or verbose

	snova = Snova(path)

	snova.setup.dirs()
	snova.setup.logging()
	snova.setup.env(python=python)
	snova.setup.config(redis=not skip_redis_config_generation, procfile=not no_procfile)
	snova.setup.patches()

	# local apps
	if clone_from:
		clone_apps_from(
			snova_path=path, clone_from=clone_from, update_app=not clone_without_update
		)

	# remote apps
	else:
		saps_path = saps_path or "https://github.com/TechSparrownova/snova.git"
		is_valid_saps_branch(saps_path=saps_path, saps_branch=saps_branch)
		get_app(
			saps_path,
			branch=saps_branch,
			snova_path=path,
			skip_assets=True,
			verbose=verbose,
			resolve_deps=False,
		)

		# fetch remote apps using config file - deprecate this!
		if apps_path:
			install_apps_from_path(apps_path, snova_path=path)

	# getting app on snova init using --install-app
	if install_app:
		get_app(
			install_app,
			branch=saps_branch,
			snova_path=path,
			skip_assets=True,
			verbose=verbose,
			resolve_deps=False,
		)

	if not skip_assets:
		build_assets(snova_path=path)

	if not no_backups:
		snova.setup.backups()


def setup_sudoers(user):
	from snova.config.lets_encrypt import get_certbot_path

	if not os.path.exists("/etc/sudoers.d"):
		os.makedirs("/etc/sudoers.d")

		set_permissions = not os.path.exists("/etc/sudoers")
		with open("/etc/sudoers", "a") as f:
			f.write("\n#includedir /etc/sudoers.d\n")

		if set_permissions:
			os.chmod("/etc/sudoers", 0o440)

	template = snova.config.env().get_template("saps_sudoers")
	saps_sudoers = template.render(
		**{
			"user": user,
			"service": which("service"),
			"systemctl": which("systemctl"),
			"nginx": which("nginx"),
			"certbot": get_certbot_path(),
		}
	)

	with open(sudoers_file, "w") as f:
		f.write(saps_sudoers)

	os.chmod(sudoers_file, 0o440)
	log(f"Sudoers was set up for user {user}", level=1)


def start(no_dev=False, concurrency=None, procfile=None, no_prefix=False, procman=None):
	program = which(procman) if procman else get_process_manager()
	if not program:
		raise Exception("No process manager found")

	os.environ["PYTHONUNBUFFERED"] = "true"
	if not no_dev:
		os.environ["DEV_SERVER"] = "true"

	command = [program, "start"]
	if concurrency:
		command.extend(["-c", concurrency])

	if procfile:
		command.extend(["-f", procfile])

	if no_prefix:
		command.extend(["--no-prefix"])

	os.execv(program, command)


def migrate_site(site, snova_path="."):
	run_saps_cmd("--site", site, "migrate", snova_path=snova_path)


def backup_site(site, snova_path="."):
	run_saps_cmd("--site", site, "backup", snova_path=snova_path)


def backup_all_sites(snova_path="."):
	from snova.snova import Snova

	for site in Snova(snova_path).sites:
		backup_site(site, snova_path=snova_path)


def fix_prod_setup_perms(snova_path=".", saps_user=None):
	from glob import glob
	from snova.snova import Snova

	saps_user = saps_user or Snova(snova_path).conf.get("saps_user")

	if not saps_user:
		print("sparrow user not set")
		sys.exit(1)

	globs = ["logs/*", "config/*"]
	for glob_name in globs:
		for path in glob(glob_name):
			uid = pwd.getpwnam(saps_user).pw_uid
			gid = grp.getgrnam(saps_user).gr_gid
			os.chown(path, uid, gid)


def setup_fonts():
	fonts_path = os.path.join("/tmp", "fonts")

	if os.path.exists("/etc/fonts_backup"):
		return

	exec_cmd("git clone https://github.com/TechSparrownova/fonts.git", cwd="/tmp")
	os.rename("/etc/fonts", "/etc/fonts_backup")
	os.rename("/usr/share/fonts", "/usr/share/fonts_backup")
	os.rename(os.path.join(fonts_path, "etc_fonts"), "/etc/fonts")
	os.rename(os.path.join(fonts_path, "usr_share_fonts"), "/usr/share/fonts")
	shutil.rmtree(fonts_path)
	exec_cmd("fc-cache -fv")
