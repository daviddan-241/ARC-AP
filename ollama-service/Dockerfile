FROM ollama/ollama:latest
# ollama image ships ENTRYPOINT ["ollama"] — override it so start.sh actually runs.
ENV OLLAMA_HOST=0.0.0.0:11434
COPY start.sh /start.sh
RUN chmod +x /start.sh
EXPOSE 11434
ENTRYPOINT ["/bin/sh", "/start.sh"]
