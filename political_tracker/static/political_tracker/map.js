/**
 * Political Tracker — Map visualisation using D3 (vendored)
 * Loads GeoJSON boundaries or dot data and colours by party from API.
 */

// Party colour mapping (must match CSS custom properties)
const PARTY_COLOURS = {
  // UK
  'Labour': '#e4003b',
  'Conservative': '#2b9be6',
  'Liberal Democrat': '#faa61a',
  'Scottish National Party': '#f2d03b',
  'SNP': '#f2d03b',
  'Reform UK': '#12b6cf',
  'Green': '#6ab023',
  'Green Party': '#6ab023',
  'Plaid Cymru': '#2e9e5b',
  'Independent': '#8d98ad',
  // US
  'Democratic': '#4a90e2',
  'Democrat': '#4a90e2',
  'Republican': '#e5484d',
  'GOP': '#e5484d',
};

const DEFAULT_COLOUR = '#8d98ad';

// US state centroids (approx lat/lng) for dot-based maps
const US_STATE_CENTROIDS = {
  'AL': [32.8, -86.8], 'AK': [64.0, -152.0], 'AZ': [34.0, -111.0], 'AR': [35.0, -92.5],
  'CA': [37.0, -119.5], 'CO': [39.0, -105.5], 'CT': [41.5, -72.5], 'DE': [39.0, -75.5],
  'FL': [28.0, -82.0], 'GA': [33.0, -83.5], 'HI': [20.0, -156.0], 'ID': [44.5, -114.5],
  'IL': [40.0, -89.5], 'IN': [40.0, -86.0], 'IA': [42.0, -93.0], 'KS': [38.5, -98.0],
  'KY': [37.5, -84.5], 'LA': [31.0, -92.0], 'ME': [45.5, -69.0], 'MD': [39.0, -76.5],
  'MA': [42.5, -71.5], 'MI': [44.5, -85.0], 'MN': [46.0, -94.0], 'MS': [33.0, -89.5],
  'MO': [38.0, -92.5], 'MT': [47.0, -110.0], 'NE': [41.5, -100.0], 'NV': [39.0, -117.0],
  'NH': [43.5, -71.5], 'NJ': [40.0, -74.5], 'NM': [34.5, -106.0], 'NY': [43.0, -74.5],
  'NC': [35.5, -80.0], 'ND': [47.5, -100.0], 'OH': [40.5, -82.5], 'OK': [35.5, -97.0],
  'OR': [44.0, -120.5], 'PA': [41.0, -77.5], 'RI': [41.5, -71.5], 'SC': [34.0, -80.5],
  'SD': [44.5, -100.0], 'TN': [35.5, -86.0], 'TX': [31.0, -99.0], 'UT': [40.0, -111.5],
  'VT': [44.0, -72.5], 'VA': [37.5, -78.5], 'WA': [47.5, -120.0], 'WV': [38.5, -80.5],
  'WI': [44.0, -90.0], 'WY': [43.0, -107.5],
  'DC': [38.9, -77.0],
};

// Map state
let mapSvg, mapG, projection, path, zoomBehaviour;
let currentCountry, currentChamber;
let geojsonData = null;
let dotData = null;
let selectedFeature = null;
let svgElement, svg;

/**
 * Initialise map
 */
async function initMap(apiUrl, geojsonUrl, country, chamber) {
  currentCountry = country;
  currentChamber = chamber;

  const container = document.getElementById('map-container');
  svgElement = document.getElementById('map-svg');
  svg = d3.select(svgElement);
  const loading = container.querySelector('.map-loading');
  const legend = document.getElementById('map-legend');
  const panel = document.getElementById('map-panel');

  if (!svgElement) return;

  // Clear previous
  svg.html('');
  legend.innerHTML = '';
  panel.hidden = true;

  try {
    // Check D3 is loaded
    if (typeof d3 === 'undefined') {
      throw new Error('D3 library not loaded - check vendor/d3.min.js');
    }

    // Ensure svg is a D3 selection
    if (!(svg instanceof d3.selection)) {
      throw new Error('SVG is not a D3 selection object');
    }

    // Load both in parallel
    const [geoRes, apiRes] = await Promise.all([
      fetch(geojsonUrl),
      fetch(apiUrl)
    ]);

    if (!geoRes.ok) throw new Error(`GeoJSON load failed: ${geoRes.status} ${geoRes.statusText}`);
    if (!apiRes.ok) throw new Error(`API load failed: ${apiRes.status} ${apiRes.statusText}`);

    geojsonData = await geoRes.json();
    const apiData = await apiRes.json();

    if (!geojsonData || !geojsonData.features) {
      throw new Error('Invalid GeoJSON: missing features');
    }

    // Check if API returns dot data (has 'dots' key) or feature data (has 'features')
    if (apiData.dots) {
      dotData = apiData.dots;
      renderDotMap(dotData, country, chamber);
    } else if (apiData.features) {
      memberData = apiData.features;
      renderGeoMap(geojsonData, memberData, country, chamber);
    } else {
      throw new Error('Invalid API response: no dots or features');
    }

    loading.hidden = true;

  } catch (err) {
    console.error('Map init failed:', err);
    loading.textContent = `Failed to load map: ${err.message}`;
  }
}

/**
 * Render dot-based map (for US Senate/House without boundary GeoJSON)
 */
function renderDotMap(dots, country, chamber) {
  // Group dots by state
  const dotsByState = {};
  dots.forEach(d => {
    if (!dotsByState[d.state]) dotsByState[d.state] = [];
    dotsByState[d.state].push(d);
  });

  // Create SVG projection for US (Albers USA)
  const width = +svgElement.attr('width') || 800;
  const height = +svgElement.attr('height') || 500;

  // Albers USA projection
  projection = d3.geoAlbersUsa()
    .scale(1000)
    .translate([width / 2, height / 2]);

  path = d3.geoPath().projection(projection);

  // Zoom behaviour
  zoomBehaviour = d3.zoom()
    .scaleExtent([1, 10])
    .on('zoom', (event) => {
      mapG.attr('transform', event.transform);
    });

  svg.call(zoomBehaviour);

  // Main group
  mapG = svg.append('g');

  // Draw dots for each state
  Object.entries(dotsByState).forEach(([state, stateDots]) => {
    const centroid = US_STATE_CENTROIDS[state];
    if (!centroid) return;

    const [lng, lat] = centroid;
    const [x, y] = projection([lng, lat]);

    if (!x || !y) return;

    // For Senate: 2 dots per state, offset them slightly
    // For House: dots at centroid
    const offset = chamber === 'senate' ? 12 : 0;

    stateDots.forEach((dot, i) => {
      const dx = chamber === 'senate' ? (i === 0 ? -offset : offset) : 0;
      const dy = chamber === 'senate' ? 0 : 0;

      mapG.append('circle')
        .attr('cx', x + dx)
        .attr('cy', y + dy)
        .attr('r', chamber === 'senate' ? 5 : 3)
        .attr('fill', PARTY_COLOURS[dot.party] || DEFAULT_COLOUR)
        .attr('stroke', '#fff')
        .attr('stroke-width', 1)
        .attr('class', 'map-dot')
        .attr('data-name', dot.name)
        .attr('data-party', dot.party)
        .attr('data-state', state)
        .style('cursor', 'pointer')
        .on('click', (event) => {
          showDotPanel(event, dot);
        })
        .on('mouseover', function() {
          d3.select(this).attr('stroke', '#000').attr('stroke-width', 2);
        })
        .on('mouseout', function() {
          d3.select(this).attr('stroke', '#fff').attr('stroke-width', 1);
        });
    });
  });

  // Add legend
  renderDotLegend(dots);
}

/**
 * Render geo-based map (for UK constituencies with GeoJSON)
 */
function renderGeoMap(geojsonData, memberData, country, chamber) {
  // Build lookup: id -> party
  const partyById = {};
  memberData.forEach(m => {
    partyById[m.id] = m.party;
  });

  // Set up SVG
  const svgNode = svgElement.node();
  let width = svgNode.clientWidth || 600;
  let height = svgNode.clientHeight || 400;

  // Always set explicit width/height as inline styles so D3 can compute projections
  svg.attr('width', width).attr('height', height);

  // Projection based on country/chamber
  projection = createProjection(country, chamber, width, height);
  path = d3.geoPath().projection(projection);

  // Zoom behaviour
  zoomBehaviour = d3.zoom()
    .scaleExtent([1, 20])
    .on('zoom', (event) => {
      mapG.attr('transform', event.transform);
    });

  svg.call(zoomBehaviour);

  // Main group
  mapG = svg.append('g');

  // Draw features
  mapG.selectAll('path')
    .data(geojsonData.features)
    .enter()
    .append('path')
    .attr('d', path)
    .attr('class', 'map-feature')
    .attr('data-id', d => d.properties.ons_code || d.properties.id || d.properties.GEOID || d.properties.name)
    .attr('fill', d => {
      const id = d.properties.ons_code || d.properties.id || d.properties.GEOID || d.properties.name;
      const party = partyById[id];
      return party ? (PARTY_COLOURS[party] || DEFAULT_COLOUR) : '#3a3a3a';
    })
    .attr('stroke', '#0a1224')
    .attr('stroke-width', 0.5)
    .style('cursor', 'pointer')
    .on('click', (event, d) => handleFeatureClick(event, d, partyById))
    .on('keydown', (event, d) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        handleFeatureClick(event, d, partyById);
      }
    })
    .attr('tabindex', 0)
    .attr('role', 'button')
    .attr('aria-label', d => {
      const id = d.properties.ons_code || d.properties.id || d.properties.GEOID || d.properties.name;
      const party = partyById[id];
      const name = memberData.find(m => m.id === id)?.name || d.properties.name || id;
      return `${name}, ${party || 'Unknown party'}`;
    });

  // Add legend
  renderLegend(partyById);
}

/**
 * Render dot legend
 */
function renderDotLegend(dots) {
  const partiesPresent = new Set(dots.map(d => d.party).filter(Boolean));
  const sortedParties = Array.from(partiesPresent).sort();

  legend.innerHTML = sortedParties.map(party => `
    <span class="legend-item">
      <span class="legend-swatch" style="background: ${PARTY_COLOURS[party] || DEFAULT_COLOUR}"></span>
      ${escapeHtml(party)}
    </span>
  `).join('');
}

/**
 * Render legend (for geo maps)
 */
function renderLegend(partyById) {
  const partiesPresent = new Set(Object.values(partyById).filter(Boolean));
  const sortedParties = Array.from(partiesPresent).sort();

  legend.innerHTML = sortedParties.map(party => `
    <span class="legend-item">
      <span class="legend-swatch" style="background: ${PARTY_COLOURS[party] || DEFAULT_COLOUR}"></span>
      ${escapeHtml(party)}
    </span>
  `).join('');
}

/**
 * Handle feature click — show panel (geo maps)
 */
function handleFeatureClick(event, feature, partyById) {
  const panel = document.getElementById('map-panel');
  const id = feature.properties.ons_code || feature.properties.id || feature.properties.GEOID || feature.properties.name;
  const party = partyById[id];
  const member = memberData.find(m => m.id === id);

  if (!member) return;

  // Update visual selection
  if (selectedFeature) {
    selectedFeature.classed('map-feature--selected', false);
  }
  selectedFeature = d3.select(event.currentTarget);
  selectedFeature.classed('map-feature--selected', true);

  // Show panel
  panel.hidden = false;
  panel.innerHTML = `
    <h4>${escapeHtml(member.name)}</h4>
    <p><span class="party-badge" style="--party-colour: ${PARTY_COLOURS[party] || DEFAULT_COLOUR}">${escapeHtml(party || 'Unknown')}</span></p>
    <p>${escapeHtml(feature.properties.name || id)}</p>
    <a href="/political_view_${currentCountry === 'US' ? 'US' : 'UK'}/member/${member.source_id}" class="btn btn--primary">View profile</a>
  `;

  // Position panel near click (clamped to viewport)
  const rect = event.currentTarget.getBoundingClientRect();
  const svgRect = document.getElementById('map-svg').getBoundingClientRect();
  panel.style.left = `${Math.min(rect.right - svgRect.left + 10, svgRect.width - 300)}px`;
  panel.style.top = `${Math.min(rect.top - svgRect.top, svgRect.height - 200)}px`;
}

/**
 * Handle dot click — show panel (dot maps)
 */
function showDotPanel(event, dot) {
  const panel = document.getElementById('map-panel');

  // Update visual selection
  mapG.selectAll('.map-dot').attr('stroke', '#fff').attr('stroke-width', 1);
  d3.select(event.currentTarget).attr('stroke', '#000').attr('stroke-width', 2);

  // Show panel
  panel.hidden = false;
  panel.innerHTML = `
    <h4>${escapeHtml(dot.name)}</h4>
    <p><span class="party-badge" style="--party-colour: ${PARTY_COLOURS[dot.party] || DEFAULT_COLOUR}">${escapeHtml(dot.party || 'Unknown')}</span></p>
    <p>${escapeHtml(dot.state)}</p>
    <a href="/political_view_${currentCountry === 'US' ? 'US' : 'UK'}/member/${dot.source_id}" class="btn btn--primary">View profile</a>
  `;

  // Position panel near click (clamped to viewport)
  const rect = event.currentTarget.getBoundingClientRect();
  const svgRect = document.getElementById('map-svg').getBoundingClientRect();
  panel.style.left = `${Math.min(rect.right - svgRect.left + 10, svgRect.width - 300)}px`;
  panel.style.top = `${Math.min(rect.top - svgRect.top, svgRect.height - 200)}px`;
}

/**
 * Create D3 projection for the given country/chamber
 */
function createProjection(country, chamber, width, height) {
  if (country === 'UK') {
    // UK: Mercator centered on UK
    return d3.geoMercator()
      .center([-2, 54])
      .scale(Math.min(width, height) * 2.5)
      .translate([width / 2, height / 2]);
  } else if (country === 'US' && chamber === 'house') {
    // US House: Albers USA
    return d3.geoAlbersUsa()
      .scale(Math.min(width, height) * 1.2)
      .translate([width / 2, height / 2]);
  } else if (country === 'US' && chamber === 'senate') {
    // US Senate: Albers USA (states)
    return d3.geoAlbersUsa()
      .scale(Math.min(width, height) * 1.2)
      .translate([width / 2, height / 2]);
  }
  // Fallback
  return d3.geoMercator().fitSize([width, height], geojsonData);
}

/**
 * Escape HTML
 */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Expose globally for tracker.js
window.initMap = initMap;

// Map-specific styles (injected)
const mapStyles = `
  .map-feature:hover { stroke: var(--accent); stroke-width: 1.5; }
  .map-feature--selected { stroke: var(--accent); stroke-width: 2; }
  .map-dot { cursor: pointer; }
  .legend-item { display: inline-flex; align-items: center; gap: 4px; margin-right: 12px; font-size: 12px; }
  .legend-swatch { width: 12px; height: 12px; border-radius: 2px; border: 1px solid var(--border); }
`;

// Inject styles
const styleSheet = document.createElement('style');
styleSheet.textContent = mapStyles;
document.head.appendChild(styleSheet);
