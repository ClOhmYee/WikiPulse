package io.wikipulse.backend.issue;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class IssueRankingsTest {
    @Test
    void rollingWindowsShareOneInstantAndClampLeapDayInKst() {
        var repository = mock(IssueQueryRepository.class);
        when(repository.findRankings(any(), any())).thenReturn(List.of());
        var service = new IssueService(mock(IssueClusterRepository.class), repository);
        var now = Instant.parse("2024-02-29T03:00:00Z");
        var data = service.rankings(now).data();
        assertThat(data.monthFrom()).isEqualTo("2024-01-30T03:00:00Z");
        assertThat(data.yearFrom()).isEqualTo("2023-02-28T03:00:00Z");
        assertThat(data.asOf()).isEqualTo(now.toString());
        assertThat(data.monthly()).isEmpty();
        assertThat(data.yearly()).isEmpty();
        verify(repository).findRankings(Instant.parse(data.monthFrom()), now);
        verify(repository).findRankings(Instant.parse(data.yearFrom()), now);
    }
}
