#!/usr/bin/env python3
"""Bootstrap the Free Edition Databricks-to-Snowflake serving path.

This is deliberately an *idempotent developer bootstrap*, not a replacement
for the Terraform production control plane. It removes the GitHub-secret and
Terraform-Cloud dependency from the single-account MVP path:

* authenticate the current Snowflake administrator with external-browser SSO;
* create the dedicated Snowflake user, roles, warehouses, schemas, and grants;
* generate a publisher key in memory and store it directly in a Databricks
  secret scope (the private key is never written to the repository);
* deploy the Databricks bundle with Snowflake publishing disabled by default.

The only interactive action is the provider-owned Snowflake SSO consent. An
automation cannot and should not bypass that identity boundary.
"""

from __future__ import annotations

import argparse
import base64
import importlib
import json
import os
import re
import subprocess
import sys
import venv
from typing import Iterable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


DEFAULT_ACCOUNT = "zcpwqmj-hd11049"
DEFAULT_DATABRICKS_PROFILE = "social-intelligence-free"
DEFAULT_SNOWFLAKE_USER = os.environ.get("SNOWFLAKE_USER", os.environ.get("USER", "gopalpatwa"))
SECRET_SCOPE = "social-intelligence"
PRIVATE_KEY_SECRET = "snowflake-private-key-base64"


def run(command: list[str], *, cwd: str | None = None, input_text: str | None = None) -> str:
    """Run a command without printing command arguments that may be secrets."""
    completed = subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"Command failed ({' '.join(command[:4])} ...):\n{completed.stderr.strip()}"
        )
    return completed.stdout


def ensure_isolated_runtime(repo_root: str) -> None:
    """Re-exec in a local venv so workstation package conflicts cannot block it."""
    if os.environ.get("SOCIAL_INTELLIGENCE_BOOTSTRAP_RUNTIME") == "1":
        return

    runtime_dir = os.path.join(repo_root, ".bootstrap-venv")
    runtime_python = os.path.join(runtime_dir, "bin", "python")
    if not os.path.exists(runtime_python):
        print("Creating isolated bootstrap runtime …")
        venv.EnvBuilder(with_pip=True).create(runtime_dir)
        run(
            [
                runtime_python,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "snowflake-connector-python>=3.12,<5",
                "cryptography>=44",
            ]
        )

    environment = {**os.environ, "SOCIAL_INTELLIGENCE_BOOTSTRAP_RUNTIME": "1"}
    os.execve(runtime_python, [runtime_python, os.path.abspath(__file__), *sys.argv[1:]], environment)


def require_snowflake_connector() -> object:
    """Load the connector from the isolated runtime."""
    try:
        return importlib.import_module("snowflake.connector")
    except ModuleNotFoundError:
        raise RuntimeError("Snowflake connector missing from the bootstrap runtime") from None


def assert_account_identifier(account: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,255}", account):
        raise ValueError("Snowflake account must be an organization-account identifier")


def databricks(command: list[str], profile: str, *, input_text: str | None = None) -> str:
    return run(["databricks", *command, "--profile", profile], input_text=input_text)


def ensure_databricks_secret_scope(profile: str) -> bool:
    scopes = json.loads(databricks(["secrets", "list-scopes", "--output", "json"], profile))
    if not any(scope.get("name") == SECRET_SCOPE for scope in scopes):
        databricks(["secrets", "create-scope", SECRET_SCOPE], profile)

    secrets = json.loads(
        databricks(["secrets", "list-secrets", SECRET_SCOPE, "--output", "json"], profile)
    )
    return any(secret.get("key") == PRIVATE_KEY_SECRET for secret in secrets)


def new_key_pair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    public_body = "".join(
        line for line in public_pem.splitlines() if not line.startswith("---")
    )
    return base64.b64encode(private_pem).decode("ascii"), public_body


def provision_snowflake(connection: object, public_key: str | None) -> None:
    """Apply a small, repeatable development control plane using admin SSO."""
    statements: Iterable[str] = (
        "CREATE ROLE IF NOT EXISTS SOCIAL_INTELLIGENCE_PUBLISHER",
        "CREATE ROLE IF NOT EXISTS SOCIAL_INTELLIGENCE_BA",
        "CREATE USER IF NOT EXISTS SVC_SOCIAL_INTELLIGENCE "
        "COMMENT = 'Databricks Social Intelligence Gold-mart publisher'",
        "CREATE DATABASE IF NOT EXISTS SOCIAL_INTELLIGENCE "
        "COMMENT = 'Governed serving database for Social Intelligence'",
        "CREATE SCHEMA IF NOT EXISTS SOCIAL_INTELLIGENCE.RAW "
        "COMMENT = 'Publisher-only staging objects'",
        "CREATE SCHEMA IF NOT EXISTS SOCIAL_INTELLIGENCE.ANALYTICS "
        "COMMENT = 'Curated BA-facing Gold marts'",
        "CREATE WAREHOUSE IF NOT EXISTS SOCIAL_INTELLIGENCE_LOAD_WH "
        "WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE "
        "INITIALLY_SUSPENDED = TRUE COMMENT = 'Social Intelligence publisher'",
        "CREATE WAREHOUSE IF NOT EXISTS SOCIAL_INTELLIGENCE_BA_WH "
        "WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 120 AUTO_RESUME = TRUE "
        "INITIALLY_SUSPENDED = TRUE COMMENT = 'Social Intelligence BA SQL'",
        "GRANT ROLE SOCIAL_INTELLIGENCE_PUBLISHER TO USER SVC_SOCIAL_INTELLIGENCE",
        "GRANT USAGE, OPERATE ON WAREHOUSE SOCIAL_INTELLIGENCE_LOAD_WH "
        "TO ROLE SOCIAL_INTELLIGENCE_PUBLISHER",
        "ALTER USER SVC_SOCIAL_INTELLIGENCE SET "
        "DEFAULT_ROLE = SOCIAL_INTELLIGENCE_PUBLISHER "
        "DEFAULT_WAREHOUSE = SOCIAL_INTELLIGENCE_LOAD_WH",
        "GRANT USAGE ON DATABASE SOCIAL_INTELLIGENCE "
        "TO ROLE SOCIAL_INTELLIGENCE_PUBLISHER",
        "GRANT USAGE, CREATE TABLE, CREATE STAGE, CREATE FILE FORMAT "
        "ON SCHEMA SOCIAL_INTELLIGENCE.RAW TO ROLE SOCIAL_INTELLIGENCE_PUBLISHER",
        "GRANT USAGE, CREATE TABLE, CREATE VIEW "
        "ON SCHEMA SOCIAL_INTELLIGENCE.ANALYTICS TO ROLE SOCIAL_INTELLIGENCE_PUBLISHER",
        "GRANT USAGE ON WAREHOUSE SOCIAL_INTELLIGENCE_BA_WH "
        "TO ROLE SOCIAL_INTELLIGENCE_BA",
        "GRANT USAGE ON DATABASE SOCIAL_INTELLIGENCE TO ROLE SOCIAL_INTELLIGENCE_BA",
        "GRANT USAGE ON SCHEMA SOCIAL_INTELLIGENCE.ANALYTICS "
        "TO ROLE SOCIAL_INTELLIGENCE_BA",
        "GRANT SELECT ON ALL TABLES IN SCHEMA SOCIAL_INTELLIGENCE.ANALYTICS "
        "TO ROLE SOCIAL_INTELLIGENCE_BA",
        "GRANT SELECT ON FUTURE TABLES IN SCHEMA SOCIAL_INTELLIGENCE.ANALYTICS "
        "TO ROLE SOCIAL_INTELLIGENCE_BA",
        "GRANT SELECT ON ALL VIEWS IN SCHEMA SOCIAL_INTELLIGENCE.ANALYTICS "
        "TO ROLE SOCIAL_INTELLIGENCE_BA",
        "GRANT SELECT ON FUTURE VIEWS IN SCHEMA SOCIAL_INTELLIGENCE.ANALYTICS "
        "TO ROLE SOCIAL_INTELLIGENCE_BA",
    )
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
        if public_key is not None:
            # The generated PEM body contains only Base64 characters, never a
            # quote, and Snowflake accepts the property as a string literal.
            cursor.execute(
                f"ALTER USER SVC_SOCIAL_INTELLIGENCE SET RSA_PUBLIC_KEY = '{public_key}'"
            )


def store_private_key(private_key: str, profile: str) -> None:
    # The CLI reads an unflagged secret from stdin. This keeps the key out of
    # shell history and process arguments.
    databricks(
        ["secrets", "put-secret", SECRET_SCOPE, PRIVATE_KEY_SECRET],
        profile,
        input_text=f"{private_key}\n",
    )


def deploy_bundle(repo_root: str, account: str, profile: str, run_initial_publish: bool) -> None:
    platform_dir = os.path.join(repo_root, "platform")
    common = [
        "--profile",
        profile,
        "-t",
        "dev",
        "--var",
        f"snowflake_account={account}",
        "--var",
        "snowflake_warehouse=SOCIAL_INTELLIGENCE_LOAD_WH",
    ]
    def deploy(publish_enabled: bool) -> None:
        run(
            [
                "databricks",
                "bundle",
                "deploy",
                *common,
                "--var",
                f"snowflake_publish_enabled={str(publish_enabled).lower()}",
            ],
            cwd=platform_dir,
        )

    deploy(False)
    if run_initial_publish:
        # This is a one-shot, guarded publish. The deployed schedule is
        # restored to disabled even if the validation or publish run fails.
        deploy(True)
        try:
            run(
                [
                    "databricks",
                    "bundle",
                    "run",
                    "social_intelligence_external_ingestion",
                    "--profile",
                    profile,
                    "-t",
                    "dev",
                ],
                cwd=platform_dir,
            )
        finally:
            deploy(False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snowflake-account", default=DEFAULT_ACCOUNT)
    parser.add_argument(
        "--snowflake-user",
        default=DEFAULT_SNOWFLAKE_USER,
        help="Snowflake administrator username; defaults to the local signed-in user",
    )
    parser.add_argument("--databricks-profile", default=DEFAULT_DATABRICKS_PROFILE)
    parser.add_argument(
        "--rotate-key",
        action="store_true",
        help="replace the Snowflake publisher public key and Databricks secret",
    )
    parser.add_argument(
        "--run-initial-publish",
        action="store_true",
        help="run the validated ingestion DAG once after deployment",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    assert_account_identifier(args.snowflake_account)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ensure_isolated_runtime(repo_root)

    existing_key = ensure_databricks_secret_scope(args.databricks_profile)
    private_key: str | None = None
    public_key: str | None = None
    if not existing_key or args.rotate_key:
        private_key, public_key = new_key_pair()

    snowflake = require_snowflake_connector()
    print("Opening Snowflake external-browser SSO for the current administrator …")
    connection = snowflake.connect(
        account=args.snowflake_account,
        user=args.snowflake_user,
        authenticator="externalbrowser",
        role="ACCOUNTADMIN",
        application="social_intelligence_bootstrap",
    )
    try:
        provision_snowflake(connection, public_key)
    finally:
        connection.close()

    if private_key is not None:
        store_private_key(private_key, args.databricks_profile)

    deploy_bundle(
        repo_root,
        args.snowflake_account,
        args.databricks_profile,
        args.run_initial_publish,
    )
    print("Bootstrap complete. Snowflake publishing remains disabled until a run is requested.")


if __name__ == "__main__":
    main()
