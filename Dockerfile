FROM debian:stable

MAINTAINER Pettai <pettai@sunet.se>

COPY . /opt/flask-tuggpg
COPY docker/setup.sh /setup.sh
COPY docker/start.sh /start.sh
RUN /setup.sh
RUN mkdir /opt/flask-tuggpg/gnupg
RUN chown -R tuggpg:tuggpg /opt/flask-tuggpg/gnupg

EXPOSE 5000

WORKDIR /opt/flask-tuggpg

CMD ["bash", "/start.sh"]
