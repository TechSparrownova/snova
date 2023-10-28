# imports - standard imports
import os
import pathlib
import re
import sys
import subprocess
from typing import List
from functools import lru_cache

# imports - module imports
from snova.exceptions import (
	InvalidRemoteException,
	InvalidBranchException,
	CommandFailedError,
	VersionNotFound,
)
from snova.app import get_repo_dir


def is_version_upgrade(app="saps", snova_path=".", branch=None):
	upstream_version = get_upstream_version(app=app, branch=branch, snova_path=snova_path)

	if not upstream_version:
		raise InvalidBranchException(
			f"Specified branch of app {app} is not in upstream remote"
		)

	local_version = get_major_version(get_current_version(app, snova_path=snova_path))
	upstream_version = get_major_version(upstream_version)

	if upstream_version > local_version:
		return (True, local_version, upstream_version)

	return (False, local_version, upstream_version)


def switch_branch(branch, apps=None, snova_path=".", upgrade=False, check_upgrade=True):
	import git
	from snova.snova import Snova
	from snova.utils import log, exec_cmd
	from snova.utils.snova import (
		build_assets,
		patch_sites,
		post_upgrade,
	)
	from snova.utils.system import backup_all_sites

	apps_dir = os.path.join(snova_path, "apps")
	version_upgrade = (False,)
	switched_apps = []

	if not apps:
		apps = [
			name for name in os.listdir(apps_dir) if os.path.isdir(os.path.join(apps_dir, name))
		]

	for app in apps:
		app_dir = os.path.join(apps_dir, app)

		if not os.path.exists(app_dir):
			log(f"{app} does not exist!", level=2)
			continue

		repo = git.Repo(app_dir)
		unshallow_flag = os.path.exists(os.path.join(app_dir, ".git", "shallow"))
		log(f"Fetching upstream {'unshallow ' if unshallow_flag else ''}for {app}")

		exec_cmd("git remote set-branches upstream  '*'", cwd=app_dir)
		exec_cmd(
			f"git fetch --all{' --unshallow' if unshallow_flag else ''} --quiet", cwd=app_dir
		)

		if check_upgrade:
			version_upgrade = is_version_upgrade(app=app, snova_path=snova_path, branch=branch)
			if version_upgrade[0] and not upgrade:
				log(
					f"Switching to {branch} will cause upgrade from"
					f" {version_upgrade[1]} to {version_upgrade[2]}. Pass --upgrade to"
					" confirm",
					level=2,
				)
				sys.exit(1)

		print("Switching for " + app)
		exec_cmd(f"git checkout -f {branch}", cwd=app_dir)

		if str(repo.active_branch) == branch:
			switched_apps.append(app)
		else:
			log(f"Switching branches failed for: {app}", level=2)

	if switched_apps:
		log(f"Successfully switched branches for: {', '.join(switched_apps)}", level=1)
		print(
			"Please run `snova update --patch` to be safe from any differences in"
			" database schema"
		)

	if version_upgrade[0] and upgrade:
		Snova(snova_path).setup.requirements()
		backup_all_sites()
		patch_sites()
		build_assets()
		post_upgrade(version_upgrade[1], version_upgrade[2])


def switch_to_branch(branch=None, apps=None, snova_path=".", upgrade=False):
	switch_branch(branch, apps=apps, snova_path=snova_path, upgrade=upgrade)


def switch_to_develop(apps=None, snova_path=".", upgrade=True):
	switch_branch("develop", apps=apps, snova_path=snova_path, upgrade=upgrade)


def get_version_from_string(contents, field="__version__"):
	match = re.search(
		r"^(\s*%s\s*=\s*['\\\"])(.+?)(['\"])" % field, contents, flags=(re.S | re.M)
	)
	if not match:
		raise VersionNotFound(f"{contents} is not a valid version")
	return match.group(2)


def get_major_version(version):
	import semantic_version

	return semantic_version.Version(version).major


def get_develop_version(app, snova_path="."):
	repo_dir = get_repo_dir(app, snova_path=snova_path)
	with open(os.path.join(repo_dir, os.path.basename(repo_dir), "hooks.py")) as f:
		return get_version_from_string(f.read(), field="develop_version")


def get_upstream_version(app, branch=None, snova_path="."):
	repo_dir = get_repo_dir(app, snova_path=snova_path)
	if not branch:
		branch = get_current_branch(app, snova_path=snova_path)

	try:
		subprocess.call(
			f"git fetch --depth=1 --no-tags upstream {branch}", shell=True, cwd=repo_dir
		)
	except CommandFailedError:
		raise InvalidRemoteException(f"Failed to fetch from remote named upstream for {app}")

	try:
		contents = subprocess.check_output(
			f"git show upstream/{branch}:{app}/__init__.py",
			shell=True,
			cwd=repo_dir,
			stderr=subprocess.STDOUT,
		)
		contents = contents.decode("utf-8")
	except subprocess.CalledProcessError as e:
		if b"Invalid object" in e.output:
			return None
		else:
			raise
	return get_version_from_string(contents)


def get_current_saps_version(snova_path="."):
	try:
		return get_major_version(get_current_version("saps", snova_path=snova_path))
	except OSError:
		return 0


def get_current_branch(app, snova_path="."):
	from snova.utils import get_cmd_output

	repo_dir = get_repo_dir(app, snova_path=snova_path)
	return get_cmd_output("basename $(git symbolic-ref -q HEAD)", cwd=repo_dir)


@lru_cache(maxsize=5)
def get_required_deps(org, name, branch, deps="hooks.py"):
	import requests
	import base64

	git_api_url = f"https://api.github.com/repos/{org}/{name}/contents/{name}/{deps}"
	params = {"ref": branch or "develop"}
	res = requests.get(url=git_api_url, params=params).json()

	if "message" in res:
		git_url = (
			f"https://raw.githubusercontent.com/{org}/{name}/{params['ref']}/{name}/{deps}"
		)
		return requests.get(git_url).text

	return base64.decodebytes(res["content"].encode()).decode()


def required_apps_from_hooks(required_deps: str, local: bool = False) -> List:
	import ast

	required_apps_re = re.compile(r"required_apps\s+=\s+(.*)")

	if local:
		required_deps = pathlib.Path(required_deps).read_text()

	_req_apps_tag = required_apps_re.search(required_deps)
	req_apps_tag = _req_apps_tag[1]
	return ast.literal_eval(req_apps_tag)


def get_remote(app, snova_path="."):
	repo_dir = get_repo_dir(app, snova_path=snova_path)
	contents = subprocess.check_output(
		["git", "remote", "-v"], cwd=repo_dir, stderr=subprocess.STDOUT
	)
	contents = contents.decode("utf-8")
	if re.findall(r"upstream[\s]+", contents):
		return "upstream"
	elif not contents:
		# if contents is an empty string => remote doesn't exist
		return False
	else:
		# get the first remote
		return contents.splitlines()[0].split()[0]


def get_app_name(snova_path: str, folder_name: str) -> str:
	"""Retrieves `name` attribute of app - equivalent to distribution name
	of python package. Fetches from pyproject.toml, setup.cfg or setup.py
	whichever defines it in that order.
	"""
	app_name = None
	apps_path = os.path.join(os.path.abspath(snova_path), "apps")

	pyproject_path = os.path.join(apps_path, folder_name, "pyproject.toml")
	config_py_path = os.path.join(apps_path, folder_name, "setup.cfg")
	setup_py_path = os.path.join(apps_path, folder_name, "setup.py")

	if os.path.exists(pyproject_path):
		try:
			from tomli import load
		except ImportError:
			from tomllib import load

		with open(pyproject_path, "rb") as f:
			app_name = load(f).get("project", {}).get("name")

	if not app_name and os.path.exists(config_py_path):
		from setuptools.config import read_configuration

		config = read_configuration(config_py_path)
		app_name = config.get("metadata", {}).get("name")

	if not app_name:
		# retrieve app name from setup.py as fallback
		with open(setup_py_path, "rb") as f:
			app_name = re.search(r'name\s*=\s*[\'"](.*)[\'"]', f.read().decode("utf-8"))[1]

	if app_name and folder_name != app_name:
		os.rename(os.path.join(apps_path, folder_name), os.path.join(apps_path, app_name))
		return app_name

	return folder_name


def check_existing_dir(snova_path, repo_name):
	cloned_path = os.path.join(snova_path, "apps", repo_name)
	dir_already_exists = os.path.isdir(cloned_path)
	return dir_already_exists, cloned_path


def get_current_version(app, snova_path="."):
	current_version = None
	repo_dir = get_repo_dir(app, snova_path=snova_path)
	config_path = os.path.join(repo_dir, "setup.cfg")
	init_path = os.path.join(repo_dir, os.path.basename(repo_dir), "__init__.py")
	setup_path = os.path.join(repo_dir, "setup.py")

	try:
		if os.path.exists(config_path):
			from setuptools.config import read_configuration

			config = read_configuration(config_path)
			current_version = config.get("metadata", {}).get("version")
		if not current_version:
			with open(init_path) as f:
				current_version = get_version_from_string(f.read())

	except (AttributeError, VersionNotFound):
		# backward compatibility
		with open(setup_path) as f:
			current_version = get_version_from_string(f.read(), field="version")

	return current_version
