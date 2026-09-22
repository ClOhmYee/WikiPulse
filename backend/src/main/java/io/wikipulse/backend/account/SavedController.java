package io.wikipulse.backend.account;

import io.wikipulse.backend.common.ApiResponse;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/me")
public class SavedController {
    private final SavedService saved;
    public SavedController(SavedService saved) { this.saved = saved; }
    private long id(Authentication auth) { return Long.parseLong(auth.getName()); }
    @GetMapping("/saved-state") public ApiResponse<?> state(Authentication auth) {
        return ApiResponse.of(saved.state(id(auth)));
    }
    @GetMapping("/bookmarks") public ApiResponse<?> issues(Authentication auth,
            @RequestParam(defaultValue="") String q, @RequestParam(required=false) Integer offset,
            @RequestParam(required=false) Integer limit) {
        return saved.list(id(auth), true, q, offset, limit);
    }
    @GetMapping("/watchlist") public ApiResponse<?> stocks(Authentication auth,
            @RequestParam(defaultValue="") String q, @RequestParam(required=false) Integer offset,
            @RequestParam(required=false) Integer limit) {
        return saved.list(id(auth), false, q, offset, limit);
    }
    @PutMapping("/bookmarks/{clusterId}") @ResponseStatus(HttpStatus.NO_CONTENT)
    public void saveIssue(Authentication auth, @PathVariable long clusterId) { saved.issue(id(auth), clusterId, true); }
    @DeleteMapping("/bookmarks/{clusterId}") @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteIssue(Authentication auth, @PathVariable long clusterId) { saved.issue(id(auth), clusterId, false); }
    @PutMapping("/watchlist/{ticker}") @ResponseStatus(HttpStatus.NO_CONTENT)
    public void saveStock(Authentication auth, @PathVariable String ticker) { saved.stock(id(auth), ticker, true); }
    @DeleteMapping("/watchlist/{ticker}") @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteStock(Authentication auth, @PathVariable String ticker) { saved.stock(id(auth), ticker, false); }
}
