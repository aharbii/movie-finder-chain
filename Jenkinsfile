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
    agent none  // Each stage defines its own Docker agent

    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds(abortPrevious: true)
    }

    environment {
        SERVICE_NAME    = 'movie-finder-chain'
        UV_IMAGE        = 'ghcr.io/astral-sh/uv:python3.13-bookworm-slim'
        DOCKER_IMAGE    = 'docker:24-dind'
    }

    stages {

        // ------------------------------------------------------------------ //
        stage('Lint') {
            agent {
                docker {
                    image "${UV_IMAGE}"
                    // Workspace root is the build context for chain (workspace member).
                    // Mount docker socket so Docker build can run in Build stage.
                    args '--mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock'
                }
            }
            steps {
                // chain is a workspace member — install from workspace root
                sh 'uv sync --frozen --group lint'
                sh 'uv run ruff check chain/src/ chain/tests/'
                sh 'uv run ruff format --check chain/src/ chain/tests/'
                sh 'uv run mypy chain/src/'
            }
        }

        // ------------------------------------------------------------------ //
        stage('Test') {
            agent {
                docker {
                    image "${UV_IMAGE}"
                }
            }
            steps {
                sh 'uv sync --frozen --group test'
                sh '''
                    uv run pytest chain/tests/ \
                        --cov=chain/src \
                        --cov-report=xml:coverage.xml \
                        --junitxml=test-results.xml \
                        -v --tb=short
                '''
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'test-results.xml'
                    cobertura coberturaReportFile: 'coverage.xml',
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
            agent {
                docker {
                    image "${DOCKER_IMAGE}"
                    args '--privileged -v /var/run/docker.sock:/var/run/docker.sock'
                }
            }
            environment {
                DOCKER_REGISTRY = credentials('docker-registry-url')
                IMAGE_TAG = "${DOCKER_REGISTRY}/${SERVICE_NAME}:${env.GIT_TAG_NAME ?: env.GIT_COMMIT.take(8)}"
            }
            steps {
                // Build from workspace root — Dockerfile needs imdbapi/ and chain/
                sh "docker build -f chain/Dockerfile -t ${IMAGE_TAG} ."
                sh "docker push ${IMAGE_TAG}"

                // Also tag as 'latest' on main branch
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
