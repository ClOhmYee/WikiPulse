package io.wikipulse.backend.account;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.time.Duration;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.session.web.http.CookieHttpSessionIdResolver;
import org.springframework.session.web.http.DefaultCookieSerializer;
import org.springframework.web.filter.OncePerRequestFilter;

@Configuration
public class SecurityConfig {
    @Bean PasswordEncoder passwordEncoder() { return new BCryptPasswordEncoder(12); }
    @Bean HttpSessionSecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }
    @Bean HttpSessionCsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }
    @Bean CookieHttpSessionIdResolver httpSessionIdResolver(
            @Value("${server.servlet.session.cookie.secure:true}") boolean secure,
            @Value("${spring.session.timeout:24h}") Duration timeout) {
        var serializer = new DefaultCookieSerializer();
        serializer.setCookieName("WIKIPULSE_SESSION");
        serializer.setCookiePath("/");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(secure);
        serializer.setSameSite("Lax");
        serializer.setCookieMaxAge(Math.toIntExact(timeout.toSeconds()));
        var resolver = new CookieHttpSessionIdResolver();
        resolver.setCookieSerializer(serializer);
        return resolver;
    }
    @Bean SecurityFilterChain securityFilterChain(HttpSecurity http,
            ObjectMapper mapper, HttpSessionSecurityContextRepository contexts,
            HttpSessionCsrfTokenRepository csrf, CookieHttpSessionIdResolver cookies) throws Exception {
        http.securityContext(c -> c.securityContextRepository(contexts))
            .csrf(c -> c.csrfTokenRepository(csrf))
            .requestCache(c -> c.disable())
            .formLogin(c -> c.disable()).httpBasic(c -> c.disable())
            .authorizeHttpRequests(c -> c
                // Container error dispatch must retain the original server error status.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/api/v1/me", "/api/v1/me/**").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/v1/**", "/actuator/health").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/v1/auth/signup", "/api/v1/auth/login").permitAll()
                .anyRequest().denyAll())
            .exceptionHandling(c -> c
                .authenticationEntryPoint((req, res, ex) -> error(mapper, res, 401, "UNAUTHORIZED"))
                .accessDeniedHandler((req, res, ex) -> error(mapper, res, 403, "FORBIDDEN")))
            .logout(c -> c.logoutUrl("/api/v1/auth/logout")
                .logoutSuccessHandler((req, res, auth) -> {
                    cookies.expireSession(req, res);
                    res.setStatus(204);
                }))
            // Renew the persistent cookie on authenticated activity, matching JDBC idle expiry.
            .addFilterBefore(new OncePerRequestFilter() {
                @Override protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res,
                        FilterChain chain) throws ServletException, IOException {
                    var auth = SecurityContextHolder.getContext().getAuthentication();
                    var session = req.getSession(false);
                    if (auth != null && auth.isAuthenticated()
                            && !(auth instanceof AnonymousAuthenticationToken) && session != null) {
                        cookies.setSessionId(req, res, session.getId());
                    }
                    chain.doFilter(req, res);
                }
            }, AuthorizationFilter.class);
        return http.build();
    }
    private static void error(ObjectMapper mapper, HttpServletResponse response, int status, String code)
            throws IOException {
        response.setStatus(status);
        response.setContentType("application/json");
        mapper.writeValue(response.getOutputStream(), Map.of("error", Map.of("code", code, "message", code)));
    }
}
