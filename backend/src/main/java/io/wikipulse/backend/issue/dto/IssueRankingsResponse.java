package io.wikipulse.backend.issue.dto;

import java.util.List;

public record IssueRankingsResponse(String asOf, String monthFrom, String yearFrom,
        List<Entry> monthly, List<Entry> yearly) {
    public record Entry(long id, String label, double pulseScore) {
        public static Entry from(Projection row) {
            return new Entry(row.getId(), row.getLabel(), row.getPulseScore());
        }
    }
    public interface Projection {
        long getId();
        String getLabel();
        double getPulseScore();
    }
}
