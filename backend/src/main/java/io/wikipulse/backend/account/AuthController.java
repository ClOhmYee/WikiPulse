package io.wikipulse.backend.account;

import io.wikipulse.backend.common.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
public class AuthController {
    public record Signup(@NotBlank @Email @Size(max=254) String email,
                         @NotBlank @Size(max=128) String password,
                         @NotBlank @Size(max=40) String displayName) {
        public Signup { if (email != null) email = email.trim(); }
    }
    public record Login(@NotBlank @Email @Size(max=254) String email,
                        @NotBlank @Size(max=128) String password) {
        public Login { if (email != null) email = email.trim(); }
    }
    private final AccountService accounts;
    private final HttpSessionSecurityContextRepository contexts;
    private final HttpSessionCsrfTokenRepository csrf;
    public AuthController(AccountService accounts, HttpSessionSecurityContextRepository contexts,
                          HttpSessionCsrfTokenRepository csrf) {
        this.accounts = accounts; this.contexts = contexts; this.csrf = csrf;
    }
    @GetMapping("/auth/csrf")
    public ApiResponse<?> csrf(CsrfToken token) {
        return ApiResponse.of(Map.of("token", token.getToken(), "headerName", token.getHeaderName()));
    }
    @PostMapping("/auth/signup") @ResponseStatus(HttpStatus.CREATED)
    public ApiResponse<?> signup(@Valid @RequestBody Signup value) {
        return ApiResponse.of(accounts.signup(value.email(), value.password(), value.displayName()));
    }
    @PostMapping("/auth/login")
    public ApiResponse<?> login(@Valid @RequestBody Login value, HttpServletRequest req, HttpServletResponse res) {
        var member = accounts.login(value.email(), value.password());
        // Only a stable member ID enters the persisted SecurityContext; never a password/hash.
        var auth = UsernamePasswordAuthenticationToken.authenticated(Long.toString(member.id()), null,
                List.of(new SimpleGrantedAuthority("ROLE_MEMBER")));
        new ChangeSessionIdAuthenticationStrategy().onAuthentication(auth, req, res);
        new CsrfAuthenticationStrategy(csrf).onAuthentication(auth, req, res);
        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);
        contexts.saveContext(context, req, res);
        return ApiResponse.of(Map.of("member", member));
    }
    @GetMapping("/me")
    public ApiResponse<?> me(Authentication auth) {
        return ApiResponse.of(accounts.member(Long.parseLong(auth.getName())));
    }
}
