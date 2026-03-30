// =============================================================================
// movie-finder-chain — Jenkins declarative pipeline
//
// Pipeline modes (Jenkins Multibranch Pipeline):
//   PR build   — every pull request: Lint + Typecheck + Test
//   Main build — push to main: same as PR + Dockerfile smoke-build
//   Tag build  — v* tag: same as main build
//
// NOTE: This image is NOT pushed to ACR. chain is an internal Python library
// imported by the backend app; only the backend app image is published to ACR.
//
// Required Jenkins plugins: Docker Pipeline, JUnit, Cobertura, Credentials Binding
// =============================================================================

pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds(abortPrevious: true)
    }

    environment {
        SERVICE_NAME = 'movie-finder-chain'
        COMPOSE_PROJECT_NAME = "movie-finder-chain-ci-${env.BUILD_NUMBER}"
    }

    stages {

        // ------------------------------------------------------------------ //
        stage('Initialize') {
            steps {
                sh 'make init'
            }
        }

        // ------------------------------------------------------------------ //
        stage('Lint + Typecheck') {
            parallel {
                stage('Lint') {
                    steps { sh 'make lint' }
                }
                stage('Typecheck') {
                    steps { sh 'make typecheck' }
                }
            }
        }

        // ------------------------------------------------------------------ //
        stage('Test') {
            steps {
                sh 'make test-coverage'
            }
            post {
                always {
                    cobertura coberturaReportFile: 'chain-coverage.xml',
                              onlyStable: false,
                              failNoReports: false
                }
            }
        }

        // ------------------------------------------------------------------ //
        // Validate Dockerfile builds correctly on main/tag, without pushing.
        stage('Build Dockerfile') {
            when {
                anyOf {
                    branch 'main'
                    buildingTag()
                }
            }
            steps {
                sh "docker build --target runtime -t ${env.SERVICE_NAME}:ci-${env.BUILD_NUMBER} ."
            }
            post {
                always {
                    sh "docker rmi ${env.SERVICE_NAME}:ci-${env.BUILD_NUMBER} || true"
                }
            }
        }

    }

    post {
        always {
            sh 'make ci-down || true'
            cleanWs()
        }
        failure {
            echo "Pipeline failed on ${env.BRANCH_NAME ?: env.GIT_TAG_NAME ?: 'unknown ref'}."
        }
    }
}
