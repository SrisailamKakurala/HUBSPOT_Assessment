import { AirtableIntegration } from '../integrations/airtable.js';
import { NotionIntegration } from '../integrations/notion.js';
import { HubspotIntegration } from '../integrations/hubspot.js';

// console.log("HubspotIntegration loaded:", HubspotIntegration);
// console.log("AirtableIntegration loaded:", AirtableIntegration);
// console.log("NotionIntegration loaded:", NotionIntegration);


export const INTEGRATION_TYPES = {
  Notion: NotionIntegration,
  Airtable: AirtableIntegration,
  Hubspot: HubspotIntegration,
};
