# legitcheck

This project now serves two different Django apps depending on the request domain:

- `webapp` is accessible via **https://legitcheck.one**
- `pcwebapp` is accessible via **https://checkerlegit.com**

The middleware `DomainRoutingMiddleware` chooses the proper URL configuration based on the host name.
