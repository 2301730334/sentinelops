// SentinelOps CI pipeline (declarative).
//
// Runs on every push to any branch (multibranch job, see jenkins/casc.yaml):
//   Checkout -> Install -> Test (JUnit + coverage) -> Build image -> Smoke test
//   -> Package -> Push to Docker Hub (main/develop only, when credentials exist)
//
// Requirements on the Jenkins controller/agent: python3 + venv, Docker CLI with
// access to a Docker engine (provided by jenkins/docker-compose.yml).

pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20', artifactNumToKeepStr: '5'))
        disableConcurrentBuilds()
    }

    environment {
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
        PYTHONDONTWRITEBYTECODE = '1'
        // DOCKERHUB_NAMESPACE is a global Jenkins env var (empty = don't push).
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    env.GIT_SHORT = sh(script: 'git rev-parse --short=7 HEAD', returnStdout: true).trim()
                    env.GIT_FULL = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
                    def ns = (env.DOCKERHUB_NAMESPACE ?: '').trim()
                    env.IMAGE_REPO = ns ? "${ns}/sentinelops" : 'sentinelops'
                    env.SMOKE_CONTAINER = "sentinelops-smoke-${env.BUILD_NUMBER}-${env.GIT_SHORT}"
                    currentBuild.displayName = "#${env.BUILD_NUMBER} ${env.GIT_SHORT}"
                }
            }
        }

        stage('Install') {
            steps {
                sh '''
                    python3 -m venv .venv
                    . .venv/bin/activate
                    pip install -q -r requirements-dev.txt
                '''
            }
        }

        stage('Test') {
            steps {
                sh '''
                    . .venv/bin/activate
                    mkdir -p reports
                    pytest --junitxml=reports/junit.xml \
                           --cov=app --cov-report=term \
                           --cov-report=xml:reports/coverage.xml \
                           --cov-report=html:reports/htmlcov
                '''
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'reports/junit.xml'
                    recordCoverage(tools: [[parser: 'COBERTURA', pattern: 'reports/coverage.xml']],
                                   sourceDirectories: [[path: 'app']])
                }
            }
        }

        stage('Build image') {
            steps {
                sh '''
                    docker build \
                        --build-arg APP_VERSION="${GIT_SHORT}" \
                        --build-arg VCS_REF="${GIT_FULL}" \
                        -t "${IMAGE_REPO}:${GIT_SHORT}" .
                    docker image ls "${IMAGE_REPO}:${GIT_SHORT}"
                '''
            }
        }

        stage('Smoke test') {
            steps {
                sh '''
                    docker run -d --name "${SMOKE_CONTAINER}" \
                        -e SECRET_KEY="smoke-${BUILD_NUMBER}-${GIT_SHORT}" \
                        -e DATABASE_URL="sqlite:////tmp/smoke.db" \
                        "${IMAGE_REPO}:${GIT_SHORT}"
                    for i in $(seq 1 30); do
                        if docker exec "${SMOKE_CONTAINER}" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=2)"; then
                            echo "Container is ready"
                            docker exec "${SMOKE_CONTAINER}" python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/readyz').read().decode())"
                            exit 0
                        fi
                        sleep 2
                    done
                    echo "Container did not become ready"; docker logs "${SMOKE_CONTAINER}"; exit 1
                '''
            }
            post {
                always {
                    sh 'docker rm -f "${SMOKE_CONTAINER}" || true'
                }
            }
        }

        stage('Package') {
            steps {
                sh '''
                    mkdir -p dist
                    git archive --format=tar.gz --prefix=sentinelops/ -o "dist/sentinelops-${GIT_SHORT}.tar.gz" HEAD
                    echo "${IMAGE_REPO}:${GIT_SHORT}" > dist/image.txt
                '''
                archiveArtifacts artifacts: 'dist/*, reports/**', fingerprint: true
            }
        }

        stage('Push image') {
            when {
                allOf {
                    anyOf { branch 'main'; branch 'develop' }
                    expression { return (env.DOCKERHUB_NAMESPACE ?: '').trim() }
                }
            }
            steps {
                withCredentials([usernamePassword(credentialsId: 'dockerhub',
                                                  usernameVariable: 'DOCKERHUB_USER',
                                                  passwordVariable: 'DOCKERHUB_TOKEN')]) {
                    sh '''
                        echo "${DOCKERHUB_TOKEN}" | docker login -u "${DOCKERHUB_USER}" --password-stdin
                        # main -> :latest, develop -> :develop, plus the immutable git-sha tag
                        if [ "${BRANCH_NAME}" = "main" ]; then CHANNEL=latest; else CHANNEL=develop; fi
                        docker tag "${IMAGE_REPO}:${GIT_SHORT}" "${IMAGE_REPO}:${CHANNEL}"
                        docker push "${IMAGE_REPO}:${GIT_SHORT}"
                        docker push "${IMAGE_REPO}:${CHANNEL}"
                    '''
                }
            }
            post {
                always {
                    sh 'docker logout || true'
                }
            }
        }
    }

    post {
        success {
            echo "Built ${env.IMAGE_REPO}:${env.GIT_SHORT}"
        }
        always {
            // Keep the Docker engine tidy on a laptop.
            sh 'docker image prune -f --filter "until=168h" || true'
        }
    }
}
