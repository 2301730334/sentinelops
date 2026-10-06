# Jenkins controller image for SentinelOps CI:
#   Jenkins LTS + Docker CLI + Python 3 (for running the test suite)
#   + plugins + Configuration-as-Code (casc.yaml), so no setup wizard is needed.
ARG JENKINS_TAG=lts-jdk21
FROM jenkins/jenkins:${JENKINS_TAG}

USER root

# Docker CLI (talks to the docker:dind service) and Python for the tests.
# hadolint ignore=DL3008
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg python3 python3-venv python3-pip git \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && chmod a+r /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends docker-ce-cli \
 && rm -rf /var/lib/apt/lists/*

USER jenkins

COPY --chown=jenkins:jenkins plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

COPY --chown=jenkins:jenkins casc.yaml /var/jenkins_conf/casc.yaml
ENV CASC_JENKINS_CONFIG=/var/jenkins_conf/casc.yaml \
    JAVA_OPTS="-Djenkins.install.runSetupWizard=false -Xmx1g"
