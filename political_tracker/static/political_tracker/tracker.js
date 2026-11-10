/**
 * Political Tracker — Main JavaScript
 * Small conveniences only; pages work without JS.
 */

// Global namespace
window.PoliticalTracker = window.PoliticalTracker || {};

/**
 * Debounce helper
 */
function debounce(fn, delay) {
  let timeoutId;
  return (...args) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
}

/**
 * Simple in-memory cache for search suggestions
 */
const searchCache = new Map();

/**
 * Fetch search suggestions from API
 */
async function fetchSuggestions(apiUrl, query, country) {
  const cacheKey = `${apiUrl}:${query}`;
  if (searchCache.has(cacheKey)) {
    return searchCache.get(cacheKey);
  }

  try {
    const url = `${apiUrl}?q=${encodeURIComponent(query)}&limit=10`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    searchCache.set(cacheKey, data.results || []);
    return data.results || [];
  } catch (err) {
    console.warn('Search suggestion fetch failed:', err);
    return [];
  }
}

/**
 * Render search results dropdown
 */
function renderSearchResults(results, container, input, country) {
  if (!results.length) {
    container.hidden = true;
    return;
  }

  container.innerHTML = results.map(r => `
    <div class="search-result-item" data-id="${r.id}" role="option">
      <div class="search-result-name">${escapeHtml(r.name)}</div>
      <div class="search-result-meta">
        ${r.party ? `<span class="party-badge" style="--party-colour: var(--party-${partyCode(r.party, country)})">${escapeHtml(r.party)}</span>` : ''}
        ${r.state ? `<span>${escapeHtml(r.state)}</span>` : ''}
        ${r.district ? `<span>${escapeHtml(r.district)}</span>` : ''}
        ${r.constituency ? `<span>${escapeHtml(r.constituency)}</span>` : ''}
        ${r.nation ? `<span>${escapeHtml(r.nation)}</span>` : ''}
        ${r.chamber ? `<span>${escapeHtml(r.chamber)}</span>` : ''}
      </div>
    </div>
  `).join('');

  container.hidden = false;

  // Click handler
  container.querySelectorAll('.search-result-item').forEach(item => {
    item.addEventListener('click', () => {
      input.value = item.dataset.id;
      container.hidden = true;
      input.focus();
    });
  });
}

/**
 * Escape HTML
 */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Map party name to CSS variable suffix
 */
function partyCode(party, country) {
  const p = party.toLowerCase();
  if (country === 'UK') {
    if (p.includes('labour')) return 'lab';
    if (p.includes('conservative')) return 'con';
    if (p.includes('liberal democrat') || p.includes('lib dem')) return 'ld';
    if (p.includes('snp')) return 'snp';
    if (p.includes('reform')) return 'ref';
    if (p.includes('green')) return 'grn';
    if (p.includes('plaid')) return 'pc';
    return 'oth';
  } else {
    if (p.includes('democratic')) return 'dem';
    if (p.includes('republican')) return 'rep';
    if (p.includes('independent')) return 'ind';
    return 'oth-us';
  }
}

/**
 * Initialise compare page search inputs
 */
window.PoliticalTracker.initCompareSearch = function(apiUrl, country) {
  const inputA = document.getElementById('member-a');
  const inputB = document.getElementById('member-b');
  const resultsA = document.getElementById('member-a-hint');
  const resultsB = document.getElementById('member-b-hint');

  if (!inputA || !inputB) return;

  const fetchDebounced = debounce(async (input, resultsContainer, value) => {
    if (value.length < 2) {
      resultsContainer.hidden = true;
      return;
    }
    const suggestions = await fetchSuggestions(apiUrl, value, country);
    renderSearchResults(suggestions, resultsContainer, input, country);
  }, 200);

  function setupInput(input, resultsContainer) {
    input.addEventListener('input', (e) => {
      fetchDebounced(input, resultsContainer, e.target.value);
    });

    input.addEventListener('focus', (e) => {
      if (e.target.value.length >= 2) {
        fetchDebounced(input, resultsContainer, e.target.value);
      }
    });

    // Hide on blur (delayed to allow click)
    input.addEventListener('blur', () => {
      setTimeout(() => { resultsContainer.hidden = true; }, 200);
    });

    // Keyboard navigation
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        resultsContainer.hidden = true;
        input.blur();
      }
    });
  }

  setupInput(inputA, resultsA);
  setupInput(inputB, resultsB);
};

/**
 * Initialise map (placeholder — actual implementation in map.js)
 */
window.PoliticalTracker.initMap = function(apiUrl, geojsonUrl, country, chamber) {
  // Delegate to map.js if loaded
  if (typeof initMap === 'function') {
    initMap(apiUrl, geojsonUrl, country, chamber);
  }
};

// Auto-initialise compare search if on compare page
document.addEventListener('DOMContentLoaded', () => {
  const compareForm = document.querySelector('.compare-form');
  if (compareForm) {
    const country = compareForm.dataset.country || 'US';
    const apiUrl = country === 'US'
      ? '/political_view_US/api/members'
      : '/political_view_UK/api/members';
    window.PoliticalTracker.initCompareSearch(apiUrl, country);
  }
});