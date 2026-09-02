import logging
import time
from collections import defaultdict
from threading import Lock

from django.http import HttpResponse

logger = logging.getLogger('security')


class LoginRateLimitMiddleware:
    """
    Limita intentos de login por IP para prevenir fuerza bruta.
    - Max 5 intentos por minuto por IP.
    - Bloquea con 429 por 60 segundos al exceder.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.max_attempts = 5
        self.window_seconds = 60
        self._attempts = defaultdict(list)
        self._lock = Lock()

    def __call__(self, request):
        if request.method == 'POST' and '/accounts/login' in request.path:
            ip = self._get_client_ip(request)
            if not self._allow_attempt(ip):
                logger.warning("Login rate limit exceeded for IP: %s", ip)
                return HttpResponse(
                    'Demasiados intentos. Espera 60 segundos.',
                    status=429
                )
            if request.method == 'POST':
                self._register_attempt(ip)
        return self.get_response(request)

    def _get_client_ip(self, request):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')

    def _allow_attempt(self, ip):
        now = time.time()
        with self._lock:
            self._attempts[ip] = [
                t for t in self._attempts[ip]
                if now - t < self.window_seconds
            ]
            return len(self._attempts[ip]) < self.max_attempts

    def _register_attempt(self, ip):
        with self._lock:
            self._attempts[ip].append(time.time())
