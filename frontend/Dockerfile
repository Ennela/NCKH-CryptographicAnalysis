FROM node:18-alpine

WORKDIR /app

# Copy package configs
COPY package.json ./

# Install dependencies (ignoring scripts/engines to speed up)
RUN npm install --legacy-peer-deps

# Copy code
COPY . .

EXPOSE 3000

ENV PORT 3000
ENV HOSTNAME "0.0.0.0"

# Default command for development
CMD ["npm", "run", "dev"]
