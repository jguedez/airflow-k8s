# airflow-k8s

## Description

Charm for Juju to deploy and manage Apache Airflow in a Kubernetes environment.

## Usage

Provision a Juju environment and a k8s model on Juju 2.9.0 or later, per Juju documentation.

Airflow needs a database to store metadata. This charm implements a db relation for
PostgreSQL for that purpose. One options would be to use
[postgresql-k8s](https://charmhub.io/postgresql-k8s/), and then a relation to it:

```
juju relate airflow-k8s:db postgresql-k8s:db
```

Once the database becomes available the charm will initialise the airflow database and
create a user for the webserver. The name of the user as well as the database can be
set via charm configuration (`webserver_username` and `database_name`), before the relation
with the database is established.

The password for the webserver user is generated automatically and can be retrieved using
the action `get-webserver-password`.

The charm supports the `ingress` relation, which can be used with
[nginx-ingress-integrator](https://charmhub.io/nginx-ingress-integrator/)

```
juju deploy nginx-ingress-integrator
juju relate airflow-k8s:ingress nginx-ingress-integrator:ingress
```

This charm will currently run an instance of the airflow webserver and scheduler using the
local executor.

DAGs can be bundled in custom images

## Developing

Create and activate a virtualenv with the development requirements:

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements-dev.txt

## Testing

The Python operator framework includes a very nice harness for testing
operator behaviour without full deployment. Just `run_tests`:

    ./run_tests
