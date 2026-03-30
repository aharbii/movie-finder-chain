// =============================================================================
// movie-finder-chain — Jenkins declarative pipeline
//
// Triggers:
//   • PR validation  — every pull request to main
//   • Release        — every git tag matching v*
//
// Required Jenkins credentials:
//   docker-registry-url  — Docker registry base URL (e.g. ghcr.io/aharbii)
//
// Required Jenkins plugins:
//   Docker Pipeline, JUnit, Cobertura, Credentials Binding
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
    }

    stages {

        // ------------------------------------------------------------------ //
        stage('Initialize') {
            steps {
                // Ensure .env exists for docker-compose (even if empty in CI)
                sh 'make init'
            }
        }

        // ------------------------------------------------------------------ //
        stage('Quality') {
            parallel {
                stage('Lint') {
                    steps {
                        sh 'make lint'
                    }
                }
                stage('Typecheck') {
                    steps {
                        sh 'make typecheck'
                    }
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
                    // Assuming coverage XML name from Makefile: chain-coverage.xml
                    cobertura coberturaReportFile: 'chain-coverage.xml',
                              onlyStable: false,
                              failNoReports: false
                }
            }
        }

        // ------------------------------------------------------------------ //
        stage('Build & Push Image') {
            // Only on main branch merges or version tags
            when {
                anyOf {
                    branch 'main'
                    buildingTag()
                }
            }
            environment {
                DOCKER_REGISTRY = credentials('docker-registry-url')
                IMAGE_TAG = "${DOCKER_REGISTRY}/${SERVICE_NAME}:${env.GIT_TAG_NAME ?: env.GIT_COMMIT.take(8)}"
            }
            steps {
                // Build using the repo-local Dockerfile
                sh "docker build -t ${IMAGE_TAG} ."
                sh "docker push ${IMAGE_TAG}"

                script {
                    if (env.BRANCH_NAME == 'main') {
                        sh "docker tag ${IMAGE_TAG} ${DOCKER_REGISTRY}/${SERVICE_NAME}:latest"
                        sh "docker push ${DOCKER_REGISTRY}/${SERVICE_NAME}:latest"
                    }
                }
            }
        }

    }

    post {
        always {
            // Standard cleanup target
            sh 'make ci-down'
            cleanWs()
        }
        failure {
            echo "Pipeline failed on branch ${env.BRANCH_NAME} — check logs above."
        }
        success {
            script {
                if (buildingTag()) {
                    echo "Release ${env.GIT_TAG_NAME} published successfully."
                }
            }
        }
    }
}
