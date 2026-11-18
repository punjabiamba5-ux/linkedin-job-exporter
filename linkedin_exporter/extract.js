() => {
  const clean = value => (value || '').replace(/\u00a0/g, ' ').trim();
  const visible = el => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const first = selectors => {
    for (const selector of selectors) {
      const el = [...document.querySelectorAll(selector)].find(visible);
      if (el && clean(el.innerText)) return clean(el.innerText);
    }
    return '';
  };
  const links = [...document.querySelectorAll('a[href]')].filter(visible);
  // The current signed-in layout uses stable component IDs, not legacy CSS classes.
  const modernJob = [...document.querySelectorAll('[componentkey^="JobDetails_AboutTheJob_"]')].find(visible);
  const jobColumn = modernJob?.closest('[data-testid="lazy-column"]');
  const top = jobColumn && [...jobColumn.children].find(e => e.querySelector('a[href*="/company/"]'));
  const topParagraphs = top ? [...top.querySelectorAll('p')].filter(visible) : [];
  const modernCompanyLink = top && [...top.querySelectorAll('a[href*="/company/"]')].find(e => visible(e) && clean(e.innerText));
  const modernPrimary = topParagraphs.find(e => /(?:ago|Just now|Today|Yesterday)/i.test(e.innerText) && /[·•]/.test(e.innerText));
  const modernTitle = topParagraphs.find(e => e !== modernPrimary && !e.querySelector('a[href*="/company/"]') && !e.closest('a[href*="/company/"]') && clean(e.innerText));
  const modernInsights = top ? [...top.querySelectorAll('a[href*="/jobs/view/"]')].filter(visible).map(e => clean(e.innerText)).filter(Boolean) : [];
  let overview = document.querySelector('[data-view-name="about-overview-section"]');
  if (!overview && /\/company\/[^/]+\/about\/?/.test(location.pathname)) {
    const heading = [...document.querySelectorAll('h2')].find(e => visible(e) && clean(e.innerText) === 'Overview');
    for (let container = heading?.parentElement; container && container !== document.body; container = container.parentElement) {
      if ([...container.querySelectorAll('p')].some(e => ['Industry', 'Company size', 'Website'].includes(clean(e.innerText)))) {
        overview = container;
        break;
      }
    }
  }
  const companyTop = document.querySelector('[componentkey^="pages.topCard."], [data-view-name="organization-top-card-section"]');
  const companyLink = links.find(a => /\/company\//.test(a.getAttribute('href')) &&
    a.closest('.job-details-jobs-unified-top-card__company-name, .jobs-unified-top-card__company-name, .topcard__org-name-link, .job-details-jobs-unified-top-card')) ||
    links.find(a => /\/company\//.test(a.getAttribute('href')) && a.closest('main'));
  const definitions = {};
  document.querySelectorAll('dt').forEach(dt => {
    if (!visible(dt)) return;
    let dd = dt.nextElementSibling;
    const values = [];
    while (dd && dd.tagName === 'DD') {
      if (visible(dd)) values.push(clean(dd.innerText));
      dd = dd.nextElementSibling;
    }
    definitions[clean(dt.innerText).replace(/:$/, '').toLowerCase()] = values.join('\n');
  });
  // Each explicit About label occupies the first child of a row; all following
  // children belong to that value (including the associated-member count).
  if (overview) {
    const labels = new Set(['website', 'phone', 'industry', 'company size', 'headquarters', 'founded', 'type', 'specialties']);
    overview.querySelectorAll('p').forEach(label => {
      const key = clean(label.innerText).toLowerCase();
      if (!visible(label) || !labels.has(key)) return;
      const row = label.parentElement.parentElement;
      if (row.children[0] !== label.parentElement) return;
      const values = [...row.children].slice(1).filter(visible).map(e => clean(e.innerText)).filter(Boolean);
      if (values.length) definitions[key] = values.join('\n');
    });
  }
  const criteria = {};
  document.querySelectorAll('.description__job-criteria-item').forEach(item => {
    const label = item.querySelector('h3');
    const value = item.querySelector('.description__job-criteria-text');
    if (visible(item) && label && value) criteria[clean(label.innerText).toLowerCase()] = clean(value.innerText);
  });
  const main = modernJob?.closest('section') || document.querySelector('section[aria-label="Primary content"]') || document.querySelector('main') || document.body;
  const modernDescription = modernJob?.querySelector('[data-testid="expandable-text-box"]');
  let descriptionText = clean(modernDescription?.innerText);
  const descriptionButton = modernDescription?.querySelector('[data-testid="expandable-text-button"]');
  if (descriptionButton) {
    const label = clean(descriptionButton.innerText);
    if (label && descriptionText.endsWith(label)) descriptionText = descriptionText.slice(0, -label.length).trim();
  }
  const legacyDescription = [...document.querySelectorAll('#job-details, .jobs-description__content, .description__text')].find(visible);
  const legacyMore = [...document.querySelectorAll('.jobs-description__footer-button, .description__text button.show-more-less-html__button')]
    .some(e => visible(e) && /(?:show|see|read) more/i.test(e.innerText + ' ' + (e.getAttribute('aria-label') || '')));
  const statusTop = top || document.querySelector('.job-details-jobs-unified-top-card, .jobs-unified-top-card, .top-card-layout');
  const statusText = clean(statusTop?.innerText);
  const closed = /\b(?:no longer accepting applications|applications are closed|this job is closed)\b/i.test(statusText);
  const applyVisible = statusTop && [...statusTop.querySelectorAll('button,a')].some(e => visible(e) && /^(?:easy )?apply\b/i.test(clean(e.innerText) || e.getAttribute('aria-label') || ''));
  return {
    application_status: closed ? 'closed' : applyVisible ? 'accepting applications' : 'unknown',
    title: clean(modernTitle?.innerText) || first(['.job-details-jobs-unified-top-card__job-title h1', '.job-details-jobs-unified-top-card__job-title', '.top-card-layout__title', 'h1']),
    company_name: clean(modernCompanyLink?.innerText) || clean(companyLink?.innerText),
    company_url: modernCompanyLink?.href || companyLink?.href || '',
    location: modernPrimary ? clean(modernPrimary.innerText.split(/[·•]/)[0]) : first(['.job-details-jobs-unified-top-card__primary-description-container .tvm__text--low-emphasis', '.jobs-unified-top-card__bullet', '.topcard__flavor--bullet']),
    primary_details: clean(modernPrimary?.innerText) || first(['.job-details-jobs-unified-top-card__primary-description-container', '.jobs-unified-top-card__primary-description', '.topcard__flavor-row']),
    posted: first(['.posted-time-ago__text', '.jobs-unified-top-card__posted-date']),
    salary: first(['.salary', '.compensation__salary', '.job-details-jobs-unified-top-card__salary-info']),
    job_insights: first(['.job-details-jobs-unified-top-card__job-insight', '.jobs-unified-top-card__job-insight']),
    insight_items: modernInsights.length ? modernInsights : [...document.querySelectorAll('.job-details-jobs-unified-top-card__job-insight, .jobs-unified-top-card__job-insight, .job-details-fit-level-preferences button')].filter(visible).map(e => clean(e.innerText)),
    description: descriptionText || first(['.jobs-description__content .jobs-box__html-content', '.jobs-description__content .jobs-description-content__text', '#job-details', '.show-more-less-html__markup', '.description__text']),
    description_expanded: modernDescription ? (!descriptionButton || !visible(descriptionButton) || /less/i.test(descriptionButton.innerText)) && !(modernDescription.clientHeight > 0 && modernDescription.scrollHeight > modernDescription.clientHeight + 2) : legacyDescription ? !legacyMore : null,
    company_about: clean(overview?.querySelector('p')?.innerText) || first(['.org-about-us-organization-description__text', '.org-about-us-organization-description p', '.org-page-details-module__card-spacing p.break-words', '.core-section-container__content p']),
    company_heading: clean(companyTop?.querySelector('h2')?.innerText) || first(['.org-top-card-summary__title', 'h1']),
    company_tagline: companyTop ? clean(companyTop.querySelector('h2 + p')?.innerText) : first(['.org-top-card-summary__tagline']),
    definitions, criteria,
    raw_text: clean(main.innerText),
    page_url: location.href
  };
}
