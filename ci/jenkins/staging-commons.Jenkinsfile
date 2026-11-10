// Commons on staging follows main. Every build of main first runs scripts/ci/deliver_staging_commons_base.sh for the
// base release (commons: pinned OpenG2P chart, --reuse-values with the staging overlay, record commons-base-delivery),
// then scripts/ci/deliver_staging_commons.sh, which
// compares what staging runs (ConfigMap commons-services-delivery: pinned chart, sha256 of the staging values and of
// the secret values) with this commit and delivers only when they differ (helm upgrade --reset-values --atomic). A
// failed delivery is therefore retried by the next build of main. No parameters, no click; pull requests never deliver.
//
// Jenkins: a multibranch job on Centre-for-Open-Societal-Systems/oan-helm, branch main only, script path
// ci/jenkins/staging-commons.Jenkinsfile. Credentials: staging-commons-deployer-kubeconfig (environments/staging/rbac/commons-deployer-rbac.yaml) and
// staging-commons-secret-values (a secret file with the values not kept in git; see docs/release/environments.md).
pipeline {
    agent { label 'oan-ci-deploy' }
    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '30'))
        timeout(time: 60, unit: 'MINUTES')
    }
    stages {
        // The base release first: Commons services run on it.
        stage('Deliver Commons base') {
            when { allOf { branch 'main'; not { changeRequest() } } }
            steps {
                withCredentials([file(credentialsId: 'staging-commons-deployer-kubeconfig', variable: 'KUBECONFIG')]) {
                    sh 'bash scripts/ci/deliver_staging_commons_base.sh'
                }
            }
        }
        stage('Deliver Commons services') {
            when { allOf { branch 'main'; not { changeRequest() } } }
            steps {
                withCredentials([
                    file(credentialsId: 'staging-commons-deployer-kubeconfig', variable: 'KUBECONFIG'),
                    file(credentialsId: 'staging-commons-secret-values', variable: 'COMMONS_SECRET_VALUES')
                ]) {
                    sh 'bash scripts/ci/deliver_staging_commons.sh "$COMMONS_SECRET_VALUES"'
                }
            }
        }
    }
}
