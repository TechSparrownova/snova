import os
import shutil
import subprocess
import unittest

from snova.app import App
from snova.snova import Snova
from snova.exceptions import InvalidRemoteException
from snova.utils import is_valid_saps_branch


class TestUtils(unittest.TestCase):
	def test_app_utils(self):
		git_url = "https://github.com/TechSparrownova/saps"
		branch = "develop"
		app = App(name=git_url, branch=branch, snova=Snova("."))
		self.assertTrue(
			all(
				[
					app.name == git_url,
					app.branch == branch,
					app.tag == branch,
					app.is_url is True,
					app.on_disk is False,
					app.org == "saps",
					app.url == git_url,
				]
			)
		)

	def test_is_valid_saps_branch(self):
		with self.assertRaises(InvalidRemoteException):
			is_valid_saps_branch(
				"https://github.com/TechSparrownova/snova.git", saps_branch="random-branch"
			)
			is_valid_saps_branch(
				"https://github.com/random/random.git", saps_branch="random-branch"
			)

		is_valid_saps_branch(
			"https://github.com/TechSparrownova/snova.git", saps_branch="develop"
		)
		is_valid_saps_branch(
			"https://github.com/TechSparrownova/snova.git", saps_branch="v13.29.0"
		)

	def test_app_states(self):
		snova_dir = "./sandbox"
		sites_dir = os.path.join(snova_dir, "sites")

		if not os.path.exists(sites_dir):
			os.makedirs(sites_dir)

		fake_snova = Snova(snova_dir)

		self.assertTrue(hasattr(fake_snova.apps, "states"))

		fake_snova.apps.states = {
			"saps": {
				"resolution": {"branch": "develop", "commit_hash": "234rwefd"},
				"version": "14.0.0-dev",
			}
		}
		fake_snova.apps.update_apps_states()

		self.assertEqual(fake_snova.apps.states, {})

		saps_path = os.path.join(snova_dir, "apps", "saps")

		os.makedirs(os.path.join(saps_path, "saps"))

		subprocess.run(["git", "init"], cwd=saps_path, capture_output=True, check=True)

		with open(os.path.join(saps_path, "saps", "__init__.py"), "w+") as f:
			f.write("__version__ = '11.0'")

		subprocess.run(["git", "add", "."], cwd=saps_path, capture_output=True, check=True)
		subprocess.run(
			["git", "config", "user.email", "snova-test_app_states@gha.com"],
			cwd=saps_path,
			capture_output=True,
			check=True,
		)
		subprocess.run(
			["git", "config", "user.name", "App States Test"],
			cwd=saps_path,
			capture_output=True,
			check=True,
		)
		subprocess.run(
			["git", "commit", "-m", "temp"], cwd=saps_path, capture_output=True, check=True
		)

		fake_snova.apps.update_apps_states(app_name="saps")

		self.assertIn("saps", fake_snova.apps.states)
		self.assertIn("version", fake_snova.apps.states["saps"])
		self.assertEqual("11.0", fake_snova.apps.states["saps"]["version"])

		shutil.rmtree(snova_dir)

	def test_ssh_ports(self):
		app = App("git@github.com:22:saps/saps")
		self.assertEqual(
			(app.use_ssh, app.org, app.repo, app.app_name), (True, "saps", "saps", "saps")
		)
