package io.wikipulse.backend.account;

import io.wikipulse.backend.common.ApiException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AccountService {
    public record Member(long id, String email, String displayName) {}
    private record Credentials(Member member, String hash) {}
    private final JdbcTemplate db;
    private final PasswordEncoder passwords;
    private final String dummyHash;
    public AccountService(JdbcTemplate db, PasswordEncoder passwords) {
        this.db = db; this.passwords = passwords;
        this.dummyHash = passwords.encode("unknown-account-timing-placeholder");
    }
    static String email(String value) { return value.trim().toLowerCase(Locale.ROOT); }
    static void validatePassword(String value) {
        if (value == null || value.codePointCount(0, value.length()) < 8
                || value.getBytes(StandardCharsets.UTF_8).length > 72) {
            throw ApiException.invalidQuery("password must be at least 8 characters and at most 72 UTF-8 bytes");
        }
    }
    public Member signup(String email, String password, String displayName) {
        validatePassword(password);
        String name = displayName.trim();
        if (name.isEmpty()) throw ApiException.invalidQuery("displayName must not be blank");
        try {
            return db.queryForObject("INSERT INTO member(email, display_name, password_hash) VALUES (?, ?, ?) RETURNING id, email, display_name",
                    (rs, row) -> new Member(rs.getLong("id"), rs.getString("email"), rs.getString("display_name")),
                    email(email), name, passwords.encode(password));
        } catch (DuplicateKeyException ex) {
            throw new ApiException(ApiException.Code.CONFLICT, "email already registered");
        }
    }
    public Member login(String email, String password) {
        // Reject overlong input before BCrypt; never truncate a credential.
        if (password == null || password.getBytes(StandardCharsets.UTF_8).length > 72)
            throw new ApiException(ApiException.Code.UNAUTHORIZED, "invalid credentials");
        var found = db.query("SELECT id, email, display_name, password_hash FROM member WHERE lower(btrim(email)) = ?",
                (rs, row) -> new Credentials(new Member(rs.getLong("id"), rs.getString("email"), rs.getString("display_name")), rs.getString("password_hash")), email(email));
        var account = found.isEmpty() ? null : found.get(0);
        boolean matches = passwords.matches(password, account == null || account.hash() == null ? dummyHash : account.hash());
        if (!matches || account == null || account.hash() == null)
            throw new ApiException(ApiException.Code.UNAUTHORIZED, "invalid credentials");
        return account.member();
    }
    public Member member(long id) {
        return db.query("SELECT id, email, display_name FROM member WHERE id = ?",
                (rs, row) -> new Member(rs.getLong("id"), rs.getString("email"), rs.getString("display_name")), id)
            .stream().findFirst().orElseThrow(() -> new ApiException(ApiException.Code.UNAUTHORIZED, "member not found"));
    }
}
