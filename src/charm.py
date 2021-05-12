#!/usr/bin/env python3
# Copyright 2021 jguedez
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""

Operator Charm for the Airflow application.

* https://airflow.apache.org/
* https://hub.docker.com/r/apache/airflow
* https://juju.is/docs/sdk

"""

import logging
import secrets

import ops.lib
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus

from charms.nginx_ingress_integrator.v0.ingress import IngressRequires

pgsql = ops.lib.use("pgsql", 1, "postgresql-charmers@lists.launchpad.net")

logger = logging.getLogger(__name__)


class AirflowCharm(CharmBase):
    """Operator Charm for the Airflow application."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        # base events
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        # db relation events
        self.db = pgsql.PostgreSQLClient(self, "db")  # 'db' relation in metadata.yaml
        self.framework.observe(
            self.db.on.database_relation_joined, self._on_database_relation_joined
        )
        self.framework.observe(self.db.on.master_changed, self._on_master_changed)
        self.framework.observe(self.db.on.standby_changed, self._on_standby_changed)

        # ingress relation events
        self.ingress = IngressRequires(self, {
            "service-hostname": "airflow.juju",
            "service-name": self.app.name,
            "service-port": 8080
        })

        # container events
        self.framework.observe(
            self.on.airflow_init_pebble_ready, self._on_airflow_init_pebble_ready
        )
        self.framework.observe(
            self.on.airflow_webserver_pebble_ready,
            self._on_airflow_webserver_pebble_ready,
        )
        self.framework.observe(
            self.on.airflow_scheduler_pebble_ready,
            self._on_airflow_scheduler_pebble_ready,
        )

        # actions events
        self.framework.observe(
            self.on.get_webserver_password_action,
            self._on_get_webserver_password_action,
        )

        self._stored.set_default(
            db_initialised=None, db_uri=None, webserver_password=None
        )

    def _on_airflow_init_pebble_ready(self, event):
        """Define a layer for airflow-init

        This container is used to initialise the database and run
        migrations, create the webserver user, etc.

        """
        # it would be better to run a one-shot command for this.
        # however this hasn't been implemented yet:
        #   https://github.com/canonical/pebble/issues/37
        # Stopping the container causes issues as well (pebble poll errors)

        if not self._stored.db_uri:
            logging.info("Cannot launch airflow-init, no db_uri yet")
            event.defer()
            return

        container = event.workload

        if self._stored.db_initialised:
            logging.info("No need to run airflow-init, db initialised already")
            return

        logging.info("Preparing airflow-init container")

        # generate webserver user password
        pwgen = secrets.token_urlsafe(16)
        self._stored.webserver_password = pwgen

        pebble_layer = self._get_common_airflow_layer("airflow-init", "version")
        environment = pebble_layer["services"]["airflow-init"]["environment"]
        environment.update(
            {
                "_AIRFLOW_DB_UPGRADE": "true",
                "_AIRFLOW_WWW_USER_CREATE": "true",
                "_AIRFLOW_WWW_USER_USERNAME": self.config["webserver_username"],
                "_AIRFLOW_WWW_USER_PASSWORD": pwgen,
                "AIRFLOW__CORE__SQL_ALCHEMY_CONN": self._stored.db_uri,
            }
        )

        container.add_layer("airflow-init", pebble_layer, combine=True)
        logging.info("Added updated layer 'airflow-init' to Pebble plan")
        container.autostart()
        self._stored.db_initialised = True

    def _on_airflow_webserver_pebble_ready(self, event):
        """Define a layer for airflow-webserver"""
        if not self._stored.db_initialised:
            logging.info("Cannot launch airflow-webserver, db not initialised yet")
            event.defer()
            return

        logging.info("Preparing airflow-webserver container")
        container = event.workload

        pebble_layer = self._get_common_airflow_layer("airflow-webserver", "webserver")
        environment = pebble_layer["services"]["airflow-webserver"]["environment"]
        environment.update(
            {
                "AIRFLOW__CORE__SQL_ALCHEMY_CONN": self._stored.db_uri,
            }
        )

        container.add_layer("airflow-webserver", pebble_layer, combine=True)
        logging.info("Added updated layer 'airflow-webserver' to Pebble plan")
        container.autostart()

    def _on_airflow_scheduler_pebble_ready(self, event):
        """Define a layer for airflow-scheduler"""
        if not self._stored.db_initialised:
            logging.info("Cannot launch airflow-scheduler, db not initialised yet")
            event.defer()
            return

        logging.info("Preparing airflow-scheduler container")
        container = event.workload

        pebble_layer = self._get_common_airflow_layer("airflow-scheduler", "scheduler")
        environment = pebble_layer["services"]["airflow-scheduler"]["environment"]
        environment.update(
            {
                "AIRFLOW__CORE__SQL_ALCHEMY_CONN": self._stored.db_uri,
            }
        )

        container.add_layer("airflow-scheduler", pebble_layer, combine=True)
        logging.info("Added updated layer 'airflow-scheduler' to Pebble plan")
        container.autostart()

    def _on_config_changed(self, _):
        """Handle the config-changed event"""

        if not self._stored.db_uri:
            logging.debug("config-changed - no db_uri available yet...blocking")
            self.unit.status = BlockedStatus("Waiting for the db to be available")
            return

        self.unit.status = ActiveStatus()

    def _on_database_relation_joined(self, event: pgsql.DatabaseRelationJoinedEvent):
        """Handle the db-relation-joined event"""
        dbname = self.config["database_name"]

        if self.model.unit.is_leader():
            # Provide requirements to the PostgreSQL server.
            event.database = dbname
        elif event.database != dbname:
            # Leader has not yet set requirements. Defer, incase this unit
            # becomes leader and needs to perform that operation.
            event.defer()
            return

        self.unit.status = BlockedStatus("Waiting for the db connection details")

    def _on_master_changed(self, event: pgsql.MasterChangedEvent):
        """Handle the db master changed event"""
        if event.database != self.config["database_name"]:
            # Leader has not yet set requirements. Wait until next event,
            # or risk connecting to an incorrect database.
            return

        # The connection to the primary database has been created,
        # changed or removed. More specific events are available, but
        # most charms will find it easier to just handle the Changed
        # events. event.master is None if the master database is not
        # available, or a pgsql.ConnectionString instance.
        if event.master:
            # store the data in both the peers relation and the stored bag
            conn_str = event.master
            db_uri = f"postgresql+psycopg2://{conn_str.user}:{conn_str.password}@{conn_str.host}:{conn_str.port}/{conn_str.dbname}"
            self._stored.db_uri = db_uri

            self.unit.status = ActiveStatus()

        # You probably want to emit an event here or call a setup routine to
        # do something useful with the libpq connection string or URI now they
        # are available.

    def _on_standby_changed(self, event: pgsql.StandbyChangedEvent):
        """Handle the db standby changed event"""
        if event.database != self.config["database_name"]:
            # Leader has not yet set requirements. Wait until next event,
            # or risk connecting to an incorrect database.
            return

        # Charms needing access to the hot standby databases can get
        # their connection details here. Applications can scale out
        # horizontally if they can make use of the read only hot
        # standby replica databases, rather than only use the single
        # master. event.stanbys will be an empty list if no hot standby
        # databases are available.
        self._stored.db_ro_uris = [c.uri for c in event.standbys]

    def _on_get_webserver_password_action(self, event):
        """Action handler that returns the current webserver user password"""
        if self._stored.webserver_password:
            msg = self._stored.webserver_password
        else:
            msg = "(not available yet)"

        event.set_results({"password": msg})

    def _get_common_airflow_layer(self, container_name, cmd):
        """Define a common base layer for airflow containers"""

        pebble_layer = {
            "summary": f"{container_name} layer",
            "description": f"pebble config layer for {container_name}",
            "services": {
                f"{container_name}": {
                    "override": "replace",
                    "summary": container_name,
                    "command": f"/entrypoint {cmd}",
                    "startup": "enabled",
                    "environment": {
                        "AIRFLOW__CORE__EXECUTOR": "LocalExecutor",
                        "AIRFLOW__CORE__FERNET_KEY": "",
                        "AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION": "true",
                        "AIRFLOW__CORE__LOAD_EXAMPLES": "true",
                        "AIRFLOW__API__AUTH_BACKEND": "airflow.api.auth.backend.basic_auth",
                    },
                }
            },
        }

        return pebble_layer


if __name__ == "__main__":
    # workaround for https://github.com/canonical/operator/issues/506
    main(AirflowCharm, use_juju_for_storage=True)
