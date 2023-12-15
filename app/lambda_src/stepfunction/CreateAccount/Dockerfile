# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

FROM public.ecr.aws/lambda/python:3.9

# Set env variables
ARG wd=/var/task/

# Copy file from local machine to image
COPY main.py helper.py git_helper requirements.txt ${wd}

# Install 2.40 version of Git
RUN yum install -y curl-devel expat-devel gettext-devel openssl-devel zlib-devel && yum clean all
RUN yum install -y gcc perl-ExtUtils-MakeMaker tar gzip.x86_64 wget make && yum clean all

WORKDIR /usr/src 
RUN wget https://www.kernel.org/pub/software/scm/git/git-2.40.0.tar.gz

WORKDIR /usr/src 
RUN tar xzf git-2.40.0.tar.gz

WORKDIR /usr/src/git-2.40.0 
RUN make prefix=/usr/local/git all

WORKDIR /usr/src/git-2.40.0 
RUN make prefix=/usr/local/git install

RUN ln -sf /usr/local/git/bin/git /usr/bin/git

# Install dependent python packages
WORKDIR ${wd}
RUN python3.9 -m pip install --no-cache-dir -r requirements.txt -t "${wd}"
RUN python3.9 -m pip install --no-cache-dir git-remote-codecommit

# Cleanup files needed to build git version
RUN yum autoremove -y perl-ExtUtils-MakeMaker tar make wget && yum clean all
RUN yum autoremove -y curl-devel expat-devel openssl-devel zlib-devel && yum clean all

RUN rm /usr/src/git-2.40.0.tar.gz

# Setup Default Healthcheck
HEALTHCHECK NONE

# Command can be overwritten by providing a different command in the template directly.
CMD ["main.lambda_handler"]
