(function () {
  const canvas = document.getElementById('login-canvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  let width, height;
  let particles = [];
  let iconsReady = false;

  const ICONS = ['\uF2D6', '\uF4DA', '\uF4CF', '\uF3CD', '\uF56C', '\uF3EE', '\uF56B'];
  // laptop, shield-check, people, graph-up-arrow, tools, folder, key
  const COLORS = ['#0156A6', '#F18020', '#0EA5E9', '#6366F1', '#22C55E'];

  function resize() {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width;
    canvas.height = height;
  }

  class Particle {
    constructor() {
      this.reset();
    }

    reset() {
      this.x = Math.random() * width;
      this.y = Math.random() * height;
      this.vx = (Math.random() - 0.5) * 0.4;
      this.vy = (Math.random() - 0.5) * 0.4;
      this.radius = Math.random() * 3 + 2;
      this.color = COLORS[Math.floor(Math.random() * COLORS.length)];
      this.icon = ICONS[Math.floor(Math.random() * ICONS.length)];
      this.pulse = Math.random() * Math.PI * 2;
      this.pulseSpeed = 0.02 + Math.random() * 0.03;
    }

    update() {
      this.x += this.vx;
      this.y += this.vy;
      this.pulse += this.pulseSpeed;

      if (this.x < -20) this.x = width + 20;
      if (this.x > width + 20) this.x = -20;
      if (this.y < -20) this.y = height + 20;
      if (this.y > height + 20) this.y = -20;
    }

    draw() {
      const pulseRadius = this.radius + Math.sin(this.pulse) * 1.2;

      // Glow
      const gradient = ctx.createRadialGradient(this.x, this.y, 0, this.x, this.y, pulseRadius * 4);
      gradient.addColorStop(0, this.color + '33'); // 20% opacity
      gradient.addColorStop(1, 'transparent');
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(this.x, this.y, pulseRadius * 4, 0, Math.PI * 2);
      ctx.fill();

      // Core
      ctx.fillStyle = this.color;
      ctx.beginPath();
      ctx.arc(this.x, this.y, pulseRadius, 0, Math.PI * 2);
      ctx.fill();

      // Icon (if font loaded)
      if (iconsReady) {
        ctx.fillStyle = '#ffffff';
        ctx.font = `${Math.max(8, pulseRadius * 1.4)}px "bootstrap-icons"`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(this.icon, this.x, this.y);
      }
    }
  }

  function initParticles() {
    const count = Math.min(60, Math.floor((width * height) / 22000));
    particles = [];
    for (let i = 0; i < count; i++) {
      particles.push(new Particle());
    }
  }

  function drawConnections() {
    const maxDist = 120;
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < maxDist) {
          const opacity = (1 - dist / maxDist) * 0.18;
          ctx.strokeStyle = `rgba(1, 86, 166, ${opacity})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.stroke();
        }
      }
    }
  }

  function animate() {
    ctx.clearRect(0, 0, width, height);
    drawConnections();
    particles.forEach(p => {
      p.update();
      p.draw();
    });
    requestAnimationFrame(animate);
  }

  function waitForIcons() {
    return document.fonts.ready.then(() => {
      iconsReady = document.fonts.check('12px "bootstrap-icons"');
    }).catch(() => {
      iconsReady = false;
    });
  }

  window.addEventListener('resize', () => {
    resize();
    initParticles();
  });

  resize();
  initParticles();
  waitForIcons().then(animate);
})();
