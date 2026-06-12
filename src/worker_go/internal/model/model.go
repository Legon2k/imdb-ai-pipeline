package model

import (
	"fmt"
	"regexp"
	"strings"
)

var imdbRegex = regexp.MustCompile(`^tt\d+$`)

// MoviePayload is the single source of truth for movie validation.
// Fields exactly match contracts/schemas.json#/definitions/MoviePayload
type MoviePayload struct {
	ImdbId   string  `json:"imdb_id"`
	Rank     int     `json:"rank"`
	Title    string  `json:"title"`
	Rating   float64 `json:"rating"` // Using float64 to safely represent decimal values
	Votes    string  `json:"votes"`
	ImageUrl *string `json:"image_url,omitempty"`
}

// Validate checks internal rules matching C# MoviePayload.Validate()
func (m *MoviePayload) Validate() error {
	if strings.TrimSpace(m.ImdbId) == "" || !imdbRegex.MatchString(m.ImdbId) {
		return fmt.Errorf("invalid imdb_id format: %s", m.ImdbId)
	}

	if m.Rank < 1 || m.Rank > 250 {
		return fmt.Errorf("rank must be between 1 and 250, got %d", m.Rank)
	}

	titleLen := len(m.Title)
	if titleLen == 0 || titleLen > 255 {
		return fmt.Errorf("title length must be 1-255, got %d", titleLen)
	}

	if m.Rating < 0.0 || m.Rating > 10.0 {
		return fmt.Errorf("rating must be between 0 and 10, got %f", m.Rating)
	}

	return nil
}
