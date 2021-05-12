APP_NAME="airflow-k8s"
CHARM_FILE="./airflow-k8s.charm"
RESOURCE_AIRFLOW="airflow=apache/airflow:2.0.2"

clean:
	rm -rf ./build/*

pack: clean
	charmcraft pack

deploy: pack
	juju deploy --resource ${RESOURCE_AIRFLOW} ${CHARM_FILE} ${APP_NAME}

refresh: pack
	juju refresh --path=${CHARM_FILE} --resource ${RESOURCE_AIRFLOW} ${APP_NAME}

.PHONY: pack pack-deploy pack-refresh
