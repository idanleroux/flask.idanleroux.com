/**
 * Political Tracker — Map visualisation using D3 (vendored)
 * Loads GeoJSON boundaries and colours by party from API.
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

// Map state
let mapSvg, mapG, projection, path, zoomBehaviour;
let currentCountry, currentChamber;
let geojsonData = null;
let memberData = null;
let selectedFeature = null;

/**
 * Initialise map
 */
async function initMap(apiUrl, geojsonUrl, country, chamber) {
  currentCountry = country;
  currentChamber = chamber;

  const container = document.getElementById('map-container');
  const svgElement = document.getElementById('map-svg');
  const svg = d3.select(svgElement);
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
      throw new Error('D3 library not loaded');
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
    memberData = apiData.features || [];

    if (!geojsonData || !geojsonData.features) {
      throw new Error('Invalid GeoJSON: missing features');
    }

    if (!memberData.length) {
      throw new Error('No member data returned from API');
    }

    // Build lookup: id -> party
    const partyById = {};
    memberData.forEach(m => {
      partyById[m.id] = m.party;
    });

    // Set up SVG with guaranteed dimensions
    const svgNode = svg.node();
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
    const features = mapG.selectAll('path')
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
    renderLegend(legend, partyById);

    loading.hidden = true;

  } catch (err) {
    console.error('Map init failed:', err);
    loading.textContent = `Failed to load map: ${err.message}`;
  }
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
 * Render legend with parties present in data
 */
function renderLegend(legendEl, partyById) {
  const partiesPresent = new Set(Object.values(partyById).filter(Boolean));
  const sortedParties = Array.from(partiesPresent).sort();

  legendEl.innerHTML = sortedParties.map(party => `
    <span class="legend-item">
      <span class="legend-swatch" style="background: ${PARTY_COLOURS[party] || DEFAULT_COLOUR}"></span>
      ${escapeHtml(party)}
    </span>
  `).join('');
}

/**
 * Handle feature click — show panel
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
  .legend-item { display: inline-flex; align-items: center; gap: 4px; margin-right: 12px; font-size: 12px; }
  .legend-swatch { width: 12px; height: 12px; border-radius: 2px; border: 1px solid var(--border); }
`;

// Inject styles
const styleSheet = document.createElement('style');
styleSheet.textContent = mapStyles;
document.head.appendChild(styleSheet);
