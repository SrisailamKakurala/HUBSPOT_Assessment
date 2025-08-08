// dataform.js

import { useEffect, useState } from 'react';
import {
  Box,
  Typography,
  CircularProgress,
  List,
  ListItem,
  ListItemText,
  Paper,
} from '@mui/material';
import axios from 'axios';

export const DataForm = ({ integrationType, credentials }) => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const formData = new FormData();
  formData.append('credentials', JSON.stringify(credentials));

  useEffect(() => {
    const fetchIntegrationItems = async () => {
      try {
        const response = await axios.post(
          `http://localhost:8000/integrations/${integrationType.toLowerCase()}/load`,
          formData
        );
        setItems(response.data || []);
      } catch (error) {
        console.error('Error loading integration items:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchIntegrationItems();
  }, [integrationType, credentials]);

  return (
    <Box mt={4}>
      <Typography variant="h6" gutterBottom>
        {integrationType} Items
      </Typography>

      {loading ? (
        <CircularProgress />
      ) : items.length > 0 ? (
        <Paper elevation={2} sx={{ maxHeight: 300, overflow: 'auto' }}>
          <List>
            {items.map((item, index) => (
              <ListItem key={item.id || index} divider>
                <ListItemText
                  primary={item.name || 'Unnamed'}
                  secondary={`Type: ${item.type}, ID: ${item.id}`}
                />
              </ListItem>
            ))}
          </List>
        </Paper>
      ) : (
        <Typography>No items found.</Typography>
      )}
    </Box>
  );
};
