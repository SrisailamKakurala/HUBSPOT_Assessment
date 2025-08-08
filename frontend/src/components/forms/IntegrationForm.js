import { useState } from 'react';
import { Box, Autocomplete, TextField, Typography } from '@mui/material';
import { INTEGRATION_TYPES } from '../../utils/constants';
import { DataForm } from './DataForm';

export const IntegrationForm = () => {
  const [integrationParams, setIntegrationParams] = useState({});
  const [user, setUser] = useState('TestUser');
  const [org, setOrg] = useState('TestOrg');
  const [currType, setCurrType] = useState(null);
  const CurrIntegration = INTEGRATION_TYPES[currType];

  // console.log(CurrIntegration)

  return (
    <Box display="flex" flexDirection="column" gap={3}>
      <Typography variant="h5" gutterBottom>
        Connect Your Integration
      </Typography>
      <TextField label="User" value={user} onChange={(e) => setUser(e.target.value)} fullWidth />
      <TextField label="Organization" value={org} onChange={(e) => setOrg(e.target.value)} fullWidth />
      <Autocomplete
        options={Object.keys(INTEGRATION_TYPES)}
        renderInput={(params) => <TextField {...params} label="Integration Type" />}
        onChange={(e, value) => setCurrType(value)}
        fullWidth
      />
      {currType && (
        <CurrIntegration
          user={user}
          org={org}
          integrationParams={integrationParams}
          setIntegrationParams={setIntegrationParams}
        />
      )}
      {integrationParams?.credentials && (
        <DataForm integrationType={integrationParams?.type} credentials={integrationParams?.credentials} />
      )}
    </Box>
  );
};
